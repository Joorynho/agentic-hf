from __future__ import annotations

import logging

from src.core.bus.collaboration_runner import CollaborationRunner
from src.core.bus.event_bus import EventBus
from src.core.models.execution import Order, RiskApprovalToken
from src.core.models.market import Bar
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

        # 5. Execution Trader
        ctx["approved_order"] = approved_order
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
