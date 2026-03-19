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
from src.core.signal_scorer import SignalScorer
from src.core.trade_outcomes import TradeOutcomeTracker
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

        self._outcome_tracker = TradeOutcomeTracker(pod_id)
        self._signal_scorer = SignalScorer(pod_id)

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

    async def run_cycle(self, bar: Bar, skip_researcher: bool = False) -> None:
        """Run one full agent cycle for a single bar.

        Args:
            bar: Market bar to process.
            skip_researcher: If True, skip the researcher step (caller already ran it).
        """
        assert all(
            a is not None for a in [
                self._researcher, self._signal, self._pm,
                self._risk, self._exec_trader, self._ops,
            ]
        ), "All 6 agents must be set before calling run_cycle()"

        ctx: dict = {"bar": bar}

        if not skip_researcher:
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
                "max_position_pct": 0.20,
                "max_leverage": 2.0,
                "position_limit_notional": round(accountant.nav * 0.20, 2),
                "positions_summary": pos_summary,
            }

        # Store performance metrics in namespace for PM/CIO access
        if accountant and hasattr(accountant, "performance_summary"):
            perf = accountant.performance_summary()
            self._ns.set("performance_summary", perf)
            ctx["performance_summary"] = perf

        # Feed closed trades to outcome tracker + signal scorer, inject into PM context
        if accountant:
            closed = accountant.closed_trades
            self._outcome_tracker.ingest(closed)
            self._signal_scorer.ingest_closed_trades(closed)

            track_record = self._outcome_tracker.format_for_prompt()
            signal_quality = self._signal_scorer.format_for_prompt()
            ctx["trade_track_record"] = track_record
            ctx["signal_quality"] = signal_quality
            self._ns.set("trade_track_record", track_record)
            self._ns.set("signal_quality", signal_quality)

        # Inject firm intelligence memo (cross-pod views) if available
        firm_memo = self._ns.get("firm_memo")
        if firm_memo:
            ctx["firm_memo"] = firm_memo

        # 3. PM (with Signal↔PM challenge, max 5 iter — handled inside pm.run_cycle)
        pm_out = await self._pm.run_cycle(ctx)  # type: ignore[union-attr]
        ctx.update(pm_out)

        # Emit pod macro view for cross-pod intelligence
        features = ctx.get("features", {})
        regime = features.get("regime", {})
        last_pm = self._ns.get("last_pm_decision") or {}
        self._ns.set("macro_view", {
            "pod_id": self._pod_id,
            "regime": regime.get("label", "Unknown"),
            "outlook": features.get("macro_outlook", "neutral"),
            "action": last_pm.get("action_summary", "holding")[:100],
        })

        # Log PM reasoning for all held positions (diary per position)
        self._log_pm_reasoning(last_pm)

        order: Order | None = ctx.get("order")

        # Universe boundary enforcement: reject trades for symbols that belong
        # exclusively to another pod's seed universe (prevents cross-pod contamination).
        if order is not None:
            from src.core.config.universes import POD_UNIVERSES
            for other_pod, other_symbols in POD_UNIVERSES.items():
                if other_pod != self._pod_id and order.symbol in other_symbols:
                    # Only block if the symbol is NOT in this pod's own universe
                    my_symbols = POD_UNIVERSES.get(self._pod_id, [])
                    if order.symbol not in my_symbols:
                        logger.warning(
                            "[%s] Rejected trade for %s — symbol belongs to %s universe, not %s",
                            self._pod_id, order.symbol, other_pod, self._pod_id,
                        )
                        order = None
                        ctx["order"] = None
                    break

        if order is None:
            # No trade proposed — still run Ops
            await self._ops.run_cycle(ctx)  # type: ignore[union-attr]
            return

        # Carry PM decision metadata so exec trader can attach it to fills
        last_pm = self._ns.get("last_pm_decision") or {}
        trades = last_pm.get("trades", [])
        matching_trade = next(
            (t for t in trades if isinstance(t, dict) and t.get("symbol") == order.symbol),
            {},
        )
        # Prefer per-trade reasoning (human-readable thesis) over the top-level
        # field which is the raw serialised TradeProposal JSON blob
        trade_reasoning = matching_trade.get("reasoning", "")
        if not trade_reasoning:
            trade_reasoning = last_pm.get("reasoning", "")
        # Strip outer JSON wrapper if it leaked through (starts with {"trades":)
        if trade_reasoning.startswith('{"trades":') or trade_reasoning.startswith("{'trades':"):
            try:
                import json as _json
                proposal = _json.loads(trade_reasoning)
                for t in proposal.get("trades", []):
                    if t.get("symbol") == order.symbol:
                        trade_reasoning = t.get("reasoning", trade_reasoning)
                        break
            except Exception:
                pass
        self._ns.set("pm_trade_metadata", {
            "reasoning": trade_reasoning[:500],
            "conviction": order.conviction,
            "strategy_tag": order.strategy_tag,
            "signal_snapshot": last_pm.get("signal_snapshot", {}),
            "stop_loss_pct": matching_trade.get("stop_loss_pct"),
            "take_profit_pct": matching_trade.get("take_profit_pct"),
            "exit_when": matching_trade.get("exit_when", ""),
            "max_hold_days": matching_trade.get("max_hold_days", 0),
        })

        # 4. Risk sign-off loop (PM↔Risk, max 10 iter)
        approved_order, exit_orders = await self._run_risk_loop_with_exits(order)

        # Execute exit orders first (stop-loss / take-profit)
        if exit_orders:
            for eo in exit_orders:
                exit_ctx = {
                    "approved_order": eo,
                    "mandate": self._ns.get("governance_mandate"),
                    "risk_halt": False,
                    "auto_exit": True,
                }
                try:
                    await self._exec_trader.run_cycle(exit_ctx)  # type: ignore[union-attr]
                    logger.info("[%s] Auto-exit executed: %s %s %.4f", self._pod_id, eo.side.value, eo.symbol, eo.quantity)
                except Exception as e:
                    logger.warning("[%s] Auto-exit failed for %s: %s", self._pod_id, eo.symbol, e)

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

    def _log_pm_reasoning(self, pm_decision: dict) -> None:
        """Log PM reasoning for all held positions after each PM decision cycle."""
        accountant = self._ns.get("accountant")
        if not accountant:
            return

        held_symbols = {
            sym for sym, pos in accountant._positions.items()
            if pos.get("quantity", 0) != 0
        }
        if not held_symbols:
            return

        now_str = datetime.now().isoformat()
        pm_trades = pm_decision.get("trades", [])
        traded_symbols: dict[str, dict] = {}
        for t in pm_trades:
            if isinstance(t, dict) and t.get("symbol"):
                traded_symbols[t["symbol"]] = t

        for sym in held_symbols:
            if sym in traded_symbols:
                t = traded_symbols[sym]
                action = (t.get("action") or "TRADE").upper()
                reasoning = t.get("reasoning", "")[:300]
                conviction = t.get("conviction", 0.0)
            else:
                action = "HOLD"
                summary = pm_decision.get("action_summary", "")
                reasoning = f"No action taken. PM summary: {summary[:200]}" if summary else "Position maintained — no action from PM this iteration"
                conviction = 0.0
            accountant.append_reasoning(sym, now_str, action, reasoning, conviction)

    async def _run_risk_loop_with_exits(self, order: Order) -> tuple[Order | None, list[Order]]:
        """Run the risk loop and collect any exit orders. Returns (approved_order, exit_orders)."""
        current_order = order
        all_exit_orders: list[Order] = []
        original_qty = order.quantity
        for i in range(5):
            risk_out = await self._risk.run_cycle({"order": current_order})  # type: ignore[union-attr]
            exit_orders = risk_out.get("exit_orders", [])
            if exit_orders and i == 0:
                all_exit_orders.extend(exit_orders)
            token: RiskApprovalToken | None = risk_out.get("token")
            if token is not None and token.is_valid():
                self._ns.set("last_risk_token", token)
                return current_order, all_exit_orders

            revised: Order | None = risk_out.get("revised_order")
            reason: str = risk_out.get("reason", "")
            if revised is None:
                logger.info("[%s] Risk rejected %s %s: %s", self._pod_id, order.side.value, order.symbol, reason)
                return None, all_exit_orders

            if revised.quantity >= current_order.quantity:
                logger.info("[%s] Risk revision converged for %s (qty unchanged at %.4f) — approving",
                            self._pod_id, order.symbol, revised.quantity)
                token = RiskApprovalToken(order_id=revised.id, pod_id=self._pod_id, expires_ms=500)
                self._ns.set("last_risk_token", token)
                return revised, all_exit_orders

            pm_accept = await self._pm.run_cycle(  # type: ignore[union-attr]
                {
                    "order": revised,
                    "risk_revision": True,
                    "risk_reason": reason,
                    "original_qty": original_qty,
                }
            )
            accepted_order = pm_accept.get("order")
            if accepted_order is None:
                logger.info("[%s] PM declined Risk revision for %s", self._pod_id, order.symbol)
                return None, all_exit_orders
            current_order = accepted_order

        return None, all_exit_orders

    async def _run_risk_loop(self, order: Order) -> Order | None:
        """PM proposes, Risk validates. Up to 5 iterations to reach agreement."""
        current_order = order
        original_qty = order.quantity
        for i in range(5):
            risk_out = await self._risk.run_cycle({"order": current_order})  # type: ignore[union-attr]
            token: RiskApprovalToken | None = risk_out.get("token")
            if token is not None and token.is_valid():
                self._ns.set("last_risk_token", token)
                return current_order

            revised: Order | None = risk_out.get("revised_order")
            reason: str = risk_out.get("reason", "")
            if revised is None:
                logger.info("[%s] Risk rejected %s %s: %s", self._pod_id, order.side.value, order.symbol, reason)
                return None

            # If Risk "revised" to the same or larger qty, it already meets limits — approve it
            if revised.quantity >= current_order.quantity:
                logger.info("[%s] Risk revision converged for %s (qty unchanged at %.4f) — approving",
                            self._pod_id, order.symbol, revised.quantity)
                token = RiskApprovalToken(order_id=revised.id, pod_id=self._pod_id, expires_ms=500)
                self._ns.set("last_risk_token", token)
                return revised

            pm_accept = await self._pm.run_cycle(  # type: ignore[union-attr]
                {
                    "order": revised,
                    "risk_revision": True,
                    "risk_reason": reason,
                    "original_qty": original_qty,
                }
            )
            accepted_order = pm_accept.get("order")
            if accepted_order is None:
                logger.info("[%s] PM declined Risk revision for %s", self._pod_id, order.symbol)
                return None
            current_order = accepted_order

        return None

    async def execute_review_orders(self, orders: list[Order]) -> list[dict]:
        """Execute orders from the daily position review through the standard risk loop.

        Each order goes through Risk validation and, if approved, the Execution Trader.
        Returns a list of result dicts with status per order.
        """
        results = []
        for order in orders:
            approved = await self._run_risk_loop(order)
            if approved is None:
                results.append({"symbol": order.symbol, "side": order.side.value,
                                "qty": order.quantity, "status": "REJECTED_BY_RISK"})
                continue

            ctx = {
                "approved_order": approved,
                "mandate": self._ns.get("governance_mandate"),
                "risk_halt": self._ns.get("governance_risk_halt", False),
                "risk_halt_reason": self._ns.get("governance_risk_halt_reason"),
            }
            try:
                await self._exec_trader.run_cycle(ctx)
                results.append({"symbol": order.symbol, "side": order.side.value,
                                "qty": order.quantity, "status": "EXECUTED"})
            except Exception as e:
                logger.warning("[%s] Review order execution failed for %s: %s",
                               self._pod_id, order.symbol, e)
                results.append({"symbol": order.symbol, "side": order.side.value,
                                "qty": order.quantity, "status": f"EXEC_ERROR: {e}"})
        return results

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
                    cost_basis=snapshot.cost_basis,
                    entry_date=snapshot.entry_date,
                    entry_thesis=snapshot.entry_thesis,
                    stop_loss_pct=snapshot.stop_loss_pct,
                    take_profit_pct=snapshot.take_profit_pct,
                    max_hold_days=snapshot.max_hold_days,
                    conviction=snapshot.conviction,
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

        # Cash and invested breakdown
        invested = total_notional
        cash_value = accountant.nav - invested

        # Build risk metrics
        risk_metrics = PodRiskMetrics(
            pod_id=self._pod_id,
            timestamp=datetime.now(),
            nav=accountant.nav,
            daily_pnl=accountant.daily_pnl,
            realized_pnl=accountant.realized_pnl,
            starting_capital=accountant.starting_capital,
            invested=round(invested, 2),
            cash=round(cash_value, 2),
            drawdown_from_hwm=drawdown,
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
        """Calculate annualized volatility from recent NAV history."""
        accountant = self._ns.get("accountant")
        if accountant and hasattr(accountant, "annualized_volatility"):
            return accountant.annualized_volatility()
        return 0.0

    def _calculate_var(self, nav: float) -> float:
        """Calculate 95% Value at Risk estimate.

        For MVP4, returns placeholder based on standard assumptions.
        Enhanced in future phases with actual distribution analysis.
        """
        # Placeholder: assume 2% daily risk at 95% confidence
        return -nav * 0.02
