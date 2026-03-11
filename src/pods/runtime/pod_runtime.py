from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from src.core.bus.collaboration_runner import CollaborationRunner
from src.core.bus.event_bus import EventBus
from src.core.models.allocation import MandateUpdate
from src.core.models.enums import PodStatus
from src.core.models.execution import Order, RiskApprovalToken, PodPosition
from src.core.models.market import Bar
from src.core.models.pod_summary import PodSummary, PodRiskMetrics, PodExposureBucket
from src.pods.base.agent import BasePodAgent
from src.pods.base.gateway import PodGateway
from src.pods.base.namespace import PodNamespace

logger = logging.getLogger(__name__)


class PodRuntime:
    """Orchestrates the 6 intra-pod agents for one pod.

    Execution order per bar tick:
      1. Researcher  — fetches/refreshes pod-specific data signals
      2. Signal      — generates feature vector from bar + research data
      3. PM          — proposes trade decision (Signal↔PM challenge loop, max 5 iter)
      4. Risk        — validates and signs off on order (PM↔Risk loop, max 10 iter)
      5. Exec Trader — submits approved order through PodGateway
      6. Ops         — heartbeat + reconciliation

    Intra-pod loops are synchronous within this call stack. No bus messages cross
    pod boundaries — only PodGateway.emit_summary() exits the isolation boundary.
    """

    def __init__(
        self,
        pod_id: str,
        namespace: PodNamespace,
        gateway: PodGateway,
        bus: EventBus,
        collaboration_runner: CollaborationRunner | None = None,
    ) -> None:
        self._pod_id = pod_id
        self._ns = namespace
        self._gateway = gateway
        self._bus = bus
        self._collab = collaboration_runner or CollaborationRunner()

        # Agents are injected after construction via set_agents()
        self._researcher: BasePodAgent | None = None
        self._signal: BasePodAgent | None = None
        self._pm: BasePodAgent | None = None
        self._risk: BasePodAgent | None = None
        self._exec_trader: BasePodAgent | None = None
        self._ops: BasePodAgent | None = None

    def set_agents(
        self,
        researcher: BasePodAgent,
        signal: BasePodAgent,
        pm: BasePodAgent,
        risk: BasePodAgent,
        exec_trader: BasePodAgent,
        ops: BasePodAgent,
    ) -> None:
        self._researcher = researcher
        self._signal = signal
        self._pm = pm
        self._risk = risk
        self._exec_trader = exec_trader
        self._ops = ops

    def set_governance_state(
        self,
        mandate: Optional[MandateUpdate] = None,
        risk_halt: bool = False,
        risk_halt_reason: Optional[str] = None,
    ) -> None:
        """Set governance state (mandate, risk halt) for execution enforcement."""
        self._ns.set("governance_mandate", mandate)
        self._ns.set("governance_risk_halt", risk_halt)
        self._ns.set("governance_risk_halt_reason", risk_halt_reason)

    async def run_cycle(self, bar: Bar) -> None:
        """Run one full agent cycle for a single bar."""
        assert all(
            a is not None for a in [
                self._researcher, self._signal, self._pm,
                self._risk, self._exec_trader, self._ops,
            ]
        ), "All 6 agents must be set before calling run_cycle()"

        ctx: dict = {"bar": bar}

        # 1. Researcher
        research_out = await self._researcher.run_cycle(ctx)  # type: ignore[union-attr]
        ctx.update(research_out)

        # 2. Signal
        signal_out = await self._signal.run_cycle(ctx)  # type: ignore[union-attr]
        ctx.update(signal_out)

        # Inject sizing context for PM (LLM-informed position sizing)
        accountant = self._ns.get("accountant")
        if accountant:
            pos_summary = []
            for sym, snap in accountant.current_positions.items():
                pos_summary.append({
                    "symbol": sym, "qty": snap.qty,
                    "notional": abs(snap.qty * snap.current_price),
                    "unrealized_pnl": snap.unrealized_pnl,
                })
            total_notional = sum(p["notional"] for p in pos_summary)
            gross_lev = total_notional / accountant.nav if accountant.nav > 0 else 0
            ctx["sizing_context"] = {
                "pod_nav": round(accountant.nav, 2),
                "available_cash": round(accountant._cash, 2),
                "current_leverage": round(gross_lev, 2),
                "max_position_pct": 0.10,
                "max_leverage": 2.0,
                "position_limit_notional": round(accountant.nav * 0.10, 2),
                "positions_summary": pos_summary,
            }

        # 3. PM (with Signal↔PM challenge, max 5 iter — handled inside pm.run_cycle)
        pm_out = await self._pm.run_cycle(ctx)  # type: ignore[union-attr]
        ctx.update(pm_out)

        order: Order | None = ctx.get("order")
        if order is None:
            # No trade proposed — still run Ops
            await self._ops.run_cycle(ctx)  # type: ignore[union-attr]
            return

        # 4. Risk sign-off loop (PM↔Risk, max 10 iter)
        approved_order = await self._run_risk_loop(order)
        if approved_order is None:
            logger.info("[%s] Order rejected by Risk after deliberation", self._pod_id)
            await self._ops.run_cycle(ctx)  # type: ignore[union-attr]
            return

        # 5. Execution Trader (with governance constraints)
        ctx["approved_order"] = approved_order
        # Inject governance state into context
        ctx["mandate"] = self._ns.get("governance_mandate")
        ctx["risk_halt"] = self._ns.get("governance_risk_halt", False)
        ctx["risk_halt_reason"] = self._ns.get("governance_risk_halt_reason")
        await self._exec_trader.run_cycle(ctx)  # type: ignore[union-attr]

        # 6. Ops
        await self._ops.run_cycle(ctx)  # type: ignore[union-attr]

    async def _run_risk_loop(self, order: Order) -> Order | None:
        """PM proposes, Risk validates. Up to 10 iterations to reach agreement."""
        current_order = order
        for i in range(10):
            risk_out = await self._risk.run_cycle({"order": current_order})  # type: ignore[union-attr]
            token: RiskApprovalToken | None = risk_out.get("token")
            if token is not None and token.is_valid():
                # Store token in namespace so ExecutionTrader can validate it
                self._ns.set("last_risk_token", token)
                return current_order

            revised: Order | None = risk_out.get("revised_order")
            if revised is None:
                # Risk hard-rejected — no revision possible
                return None
            # PM accepts revision
            pm_accept = await self._pm.run_cycle(  # type: ignore[union-attr]
                {"order": revised, "risk_revision": True}
            )
            current_order = pm_accept.get("order") or revised

        return None  # max iterations reached without approval

    async def get_summary(self) -> PodSummary:
        """Generate PodSummary with real trading data from PortfolioAccountant.

        Returns:
            PodSummary with current NAV, positions, risk metrics, and exposure buckets.
        """
        # Retrieve PortfolioAccountant from pod namespace
        accountant = self._ns.get("accountant")
        if accountant is None:
            # Fallback: return empty summary (pod not fully initialized)
            logger.warning("[%s] PortfolioAccountant not found in namespace", self._pod_id)
            return PodSummary(
                pod_id=self._pod_id,
                timestamp=datetime.now(),
                status=PodStatus.INITIALIZING,
                risk_metrics=PodRiskMetrics(
                    pod_id=self._pod_id,
                    timestamp=datetime.now(),
                    nav=0.0,
                    daily_pnl=0.0,
                    drawdown_from_hwm=0.0,
                    current_vol_ann=0.0,
                    gross_leverage=0.0,
                    net_leverage=0.0,
                    var_95_1d=0.0,
                    es_95_1d=0.0,
                ),
                exposure_buckets=[],
                expected_return_estimate=0.0,
                turnover_daily_pct=0.0,
                heartbeat_ok=True,
                positions=[],
                error_message="PortfolioAccountant not initialized",
            )

        # Build positions list from accountant
        positions: list[PodPosition] = []
        for symbol, snapshot in accountant.current_positions.items():
            positions.append(
                PodPosition(
                    symbol=symbol,
                    qty=snapshot.qty,
                    current_price=snapshot.current_price,
                    unrealized_pnl=snapshot.unrealized_pnl,
                    notional=snapshot.notional,
                )
            )

        # Calculate leverage
        total_notional = sum(abs(p.notional) for p in positions)
        gross_leverage = total_notional / accountant.nav if accountant.nav > 0 else 0.0

        # Calculate net leverage (long notional - short notional) / NAV
        long_notional = sum(p.notional for p in positions if p.notional > 0)
        short_notional = sum(abs(p.notional) for p in positions if p.notional < 0)
        net_leverage = (long_notional - short_notional) / accountant.nav if accountant.nav > 0 else 0.0

        # Calculate volatility and VaR from price history (simplified)
        # For MVP4, use placeholder values; will enhance in future phases
        vol_ann = self._calculate_volatility()
        var_95 = self._calculate_var(accountant.nav)

        # Calculate drawdown from HWM
        drawdown = accountant.drawdown_from_hwm()

        # Build exposure buckets (simplified: all US equities for MVP4)
        exposure_buckets = []
        if total_notional > 0 and accountant.nav > 0:
            exposure_pct = total_notional / accountant.nav
            exposure_buckets.append(
                PodExposureBucket(
                    asset_class="US_EQUITIES",
                    direction="long" if long_notional >= 0 else "short",
                    notional_pct_nav=exposure_pct,
                )
            )

        # Build risk metrics
        risk_metrics = PodRiskMetrics(
            pod_id=self._pod_id,
            timestamp=datetime.now(),
            nav=accountant.nav,
            daily_pnl=accountant.daily_pnl,
            starting_capital=accountant.starting_capital,
            drawdown_from_hwm=max(0.0, drawdown),  # Clamp to non-negative
            current_vol_ann=vol_ann,
            gross_leverage=gross_leverage,
            net_leverage=net_leverage,
            var_95_1d=var_95,
            es_95_1d=var_95 * 1.25,  # Expected shortfall approximation
        )

        # Determine pod status
        status = PodStatus.ACTIVE

        # Create and return summary
        summary = PodSummary(
            pod_id=self._pod_id,
            timestamp=datetime.now(),
            status=status,
            risk_metrics=risk_metrics,
            exposure_buckets=exposure_buckets,
            expected_return_estimate=0.0,  # Placeholder; calculated by PM agent
            turnover_daily_pct=0.0,  # Placeholder; calculated from order history
            heartbeat_ok=True,
            positions=positions,
            error_message=None,
        )

        logger.debug(
            "[%s] Generated summary: NAV=$%.2f, positions=%d, leverage=%.2fx",
            self._pod_id, accountant.nav, len(positions), gross_leverage
        )

        return summary

    def _calculate_volatility(self) -> float:
        """Calculate annualized volatility from recent NAV history.

        For MVP4, returns placeholder 0.0. Enhanced in future phases
        with actual return calculations.
        """
        return 0.0

    def _calculate_var(self, nav: float) -> float:
        """Calculate 95% Value at Risk estimate.

        For MVP4, returns placeholder based on standard assumptions.
        Enhanced in future phases with actual distribution analysis.
        """
        # Placeholder: assume 2% daily risk at 95% confidence
        return -nav * 0.02
