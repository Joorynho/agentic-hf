from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.core.bus.event_bus import EventBus
from src.core.models.enums import EventType, PodStatus
from src.core.models.messages import AgentMessage, Event
from src.core.models.pod_summary import PodSummary

logger = logging.getLogger(__name__)

_AGENT_ID = "cro"

# Firm-level hard limits
_FIRM_VAR_LIMIT = 0.03        # 3% firm VaR (sum across pods)
_FIRM_LEVERAGE_LIMIT = 1.5    # 1.5x firm gross leverage
_WARN_DRAWDOWN_PCT = 0.80     # warn at 80% of pod limit
_HALT_DRAWDOWN_PCT = 0.95     # auto-halt at 95% of pod limit


class CROAgent:
    """Chief Risk Officer — always rule-based, never LLM.

    Enforces hard limits across all 5 pods simultaneously.
    Participates in governance loops (Loop 5: interrogation, Loop 6: deliberation).

    Rule: Risk enforcement is always code. Kill-switches are deterministic.
    """

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._active_alerts: dict[str, str] = {}  # pod_id → alert_type

    @property
    def agent_id(self) -> str:
        return _AGENT_ID

    async def check_all_pods(self, pod_summaries: list[PodSummary]) -> list[str]:
        """Run full firm-level risk checks. Returns list of pod_ids with breaches."""
        breached: list[str] = []

        # Per-pod checks
        for summary in pod_summaries:
            breach = await self._check_pod(summary)
            if breach:
                breached.append(summary.pod_id)

        # Firm-level aggregate checks
        await self._check_firm_aggregate(pod_summaries)

        return breached

    async def _check_pod(self, summary: PodSummary) -> bool:
        """Check individual pod limits. Returns True if hard breach detected."""
        m = summary.risk_metrics

        # Drawdown check
        from src.core.models.config import RiskBudget  # avoid circular at module level
        dd_ratio = m.drawdown_from_hwm  # already a ratio (e.g. 0.05 = 5%)

        # Warning at 80% of max_drawdown (we don't have config here so use absolute thresholds)
        if dd_ratio > 0.10:  # 10% absolute drawdown → critical
            await self._publish_alert(
                summary.pod_id,
                f"Drawdown {dd_ratio:.1%} exceeds 10% limit",
                severity="critical",
            )
            if dd_ratio > 0.12:  # 12% → kill switch
                await self._issue_kill_switch(summary.pod_id, f"Drawdown {dd_ratio:.1%} > 12%")
            return True  # any drawdown >10% is a hard breach

        # Leverage check
        if m.gross_leverage > 2.0:
            await self._publish_alert(
                summary.pod_id,
                f"Gross leverage {m.gross_leverage:.2f}x exceeds 2.0x limit",
                severity="critical",
            )
            return True

        # VaR check
        if m.var_95_1d > 0.025:
            await self._publish_alert(
                summary.pod_id,
                f"VaR {m.var_95_1d:.3f} exceeds 2.5% limit",
                severity="warning",
            )

        return False

    async def _check_firm_aggregate(self, summaries: list[PodSummary]) -> None:
        """Check firm-level aggregates: total VaR and total leverage."""
        active = [s for s in summaries if s.status != PodStatus.HALTED]

        total_var = sum(s.risk_metrics.var_95_1d for s in active)
        if total_var > _FIRM_VAR_LIMIT:
            await self._publish_alert(
                "firm",
                f"Firm VaR {total_var:.3f} exceeds {_FIRM_VAR_LIMIT:.1%} limit",
                severity="critical",
            )

        avg_leverage = (
            sum(s.risk_metrics.gross_leverage for s in active) / len(active)
            if active else 0.0
        )
        if avg_leverage > _FIRM_LEVERAGE_LIMIT:
            await self._publish_alert(
                "firm",
                f"Avg firm leverage {avg_leverage:.2f}x exceeds {_FIRM_LEVERAGE_LIMIT}x limit",
                severity="warning",
            )

    async def firm_kill_switch(self, reason: str) -> None:
        """Halt the entire firm. All pods receive KILL_SWITCH."""
        logger.critical("[cro] FIRM KILL SWITCH: %s", reason)
        msg = AgentMessage(
            timestamp=datetime.now(timezone.utc),
            sender=_AGENT_ID,
            recipient="*",
            topic="risk.alert",
            payload={"scope": "firm", "reason": reason, "action": "kill"},
        )
        await self._bus.publish("risk.alert", msg, publisher_id="risk_manager")

    async def handle_governance_message(self, msg: AgentMessage) -> AgentMessage | None:
        """Respond in governance loops. CRO provides hard constraint validation."""
        action = msg.payload.get("action", "")

        if action in ("cio_proposal", "ceo_strategy"):
            # Validate proposed allocations against risk limits
            proposed = msg.payload.get("proposed_allocations", {})
            violations = [
                pid for pid, pct in proposed.items()
                if pct > 0.50  # no single pod >50%
            ]
            if violations:
                return AgentMessage(
                    timestamp=datetime.now(timezone.utc),
                    sender=_AGENT_ID,
                    recipient=msg.sender,
                    topic=msg.topic,
                    payload={
                        "consensus": False,
                        "outcome": {},
                        "response": f"CRO rejects: {violations} exceed 50% pod limit",
                        "violations": violations,
                    },
                    correlation_id=msg.id,
                )
            return AgentMessage(
                timestamp=datetime.now(timezone.utc),
                sender=_AGENT_ID,
                recipient=msg.sender,
                topic=msg.topic,
                payload={
                    "consensus": True,
                    "outcome": {"action": "cro_approved"},
                    "response": "CRO approves — no risk limit violations",
                },
                correlation_id=msg.id,
            )

        if action == "pod_risk_query":
            # Loop 5: CRO asks pod risk agent for exposure breakdown
            return AgentMessage(
                timestamp=datetime.now(timezone.utc),
                sender=_AGENT_ID,
                recipient=msg.sender,
                topic=msg.topic,
                payload={
                    "consensus": True,
                    "outcome": {"action": "exposure_received"},
                    "response": "CRO acknowledges exposure breakdown",
                },
                correlation_id=msg.id,
            )

        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _publish_alert(self, pod_id: str, message: str, severity: str) -> None:
        logger.warning("[cro] ALERT [%s] %s: %s", severity.upper(), pod_id, message)
        msg = AgentMessage(
            timestamp=datetime.now(timezone.utc),
            sender=_AGENT_ID,
            recipient="*",
            topic="risk.alert",
            payload={"pod_id": pod_id, "message": message, "severity": severity, "action": "alert"},
        )
        await self._bus.publish("risk.alert", msg, publisher_id="risk_manager")
        self._active_alerts[pod_id] = severity

    async def _issue_kill_switch(self, pod_id: str, reason: str) -> None:
        logger.critical("[cro] KILL SWITCH -> %s: %s", pod_id, reason)
        msg = AgentMessage(
            timestamp=datetime.now(timezone.utc),
            sender=_AGENT_ID,
            recipient="*",
            topic="risk.alert",
            payload={"pod_id": pod_id, "reason": reason, "scope": "pod", "action": "kill"},
        )
        await self._bus.publish("risk.alert", msg, publisher_id="risk_manager")
