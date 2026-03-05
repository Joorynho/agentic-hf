from __future__ import annotations
from datetime import datetime
from src.core.bus.event_bus import EventBus
from src.core.models.pod_summary import PodSummary
from src.core.models.config import RiskBudget
from src.core.models.messages import AgentMessage

class RiskManager:
    """Rule-based. Never delegates limit enforcement to an LLM."""

    def __init__(self, bus: EventBus):
        self._bus = bus

    async def check_pod(self, summary: PodSummary, budget: RiskBudget) -> list[str]:
        """Returns list of breach reasons. Empty = within limits."""
        m = summary.risk_metrics
        breaches = []

        if m.drawdown_from_hwm < -budget.max_drawdown:
            breaches.append(f"drawdown {m.drawdown_from_hwm:.1%} exceeds limit {-budget.max_drawdown:.1%}")
        if m.current_vol_ann > budget.target_vol * 1.5:
            breaches.append(f"vol {m.current_vol_ann:.1%} exceeds 1.5x target {budget.target_vol:.1%}")
        if m.gross_leverage > budget.max_leverage:
            breaches.append(f"leverage {m.gross_leverage:.2f}x exceeds limit {budget.max_leverage:.2f}x")
        if m.var_95_1d > budget.var_limit_95:
            breaches.append(f"VaR {m.var_95_1d:.1%} exceeds limit {budget.var_limit_95:.1%}")

        if breaches:
            await self._send_halt(summary.pod_id, breaches)
        return breaches

    async def _send_halt(self, pod_id: str, reasons: list[str]) -> None:
        msg = AgentMessage(
            timestamp=datetime.now(),
            sender="risk_manager",
            recipient=f"pod.{pod_id}.gateway",
            topic="risk.alert",
            payload={"action": "halt", "pod_id": pod_id, "reasons": reasons})
        await self._bus.publish("risk.alert", msg, publisher_id="risk_manager")

    async def firm_kill_switch(self, authorized_by: str, reason: str) -> None:
        msg = AgentMessage(
            timestamp=datetime.now(),
            sender="risk_manager",
            recipient="broadcast",
            topic="risk.alert",
            payload={"action": "firm_kill_switch", "authorized_by": authorized_by, "reason": reason})
        await self._bus.publish("risk.alert", msg, publisher_id="risk_manager")
