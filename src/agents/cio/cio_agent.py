from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from src.backtest.accounting.capital_allocator import CapitalAllocator
from src.core.bus.event_bus import EventBus
from src.core.llm import has_llm_key, llm_chat, extract_json
from src.core.models.allocation import AllocationRecord
from src.core.models.messages import AgentMessage
from src.core.models.pod_summary import PodSummary
from src.mission_control.session_logger import SessionLogger

logger = logging.getLogger(__name__)

_AGENT_ID = "cio"


class CIOAgent:
    """Firm-level CIO: capital allocation across pods. Participates in Loop 4/7.

    LLM mode: uses Qwen 3 32B via OpenRouter (falls back to OpenAI if no OpenRouter key).
    Fallback: equal-weight or drift-correction rule.
    """

    def __init__(self, bus: EventBus, allocator: CapitalAllocator, session_logger: SessionLogger | None = None) -> None:
        self._bus = bus
        self._allocator = allocator
        self._session_logger = session_logger
        self._has_llm = has_llm_key()

    @property
    def agent_id(self) -> str:
        return _AGENT_ID

    async def rebalance(
        self,
        pod_summaries: list[PodSummary],
        ceo_narrative: str = "",
        cro_constraints: dict | None = None,
    ) -> list[AllocationRecord]:
        """Propose and apply rebalancing. Returns applied AllocationRecords."""
        if self._has_llm:
            records = await self._llm_allocation(pod_summaries, ceo_narrative, cro_constraints or {})
        else:
            records = self._rule_based_allocation(pod_summaries)

        ok, reason = self._allocator.validate(records)
        if not ok:
            logger.warning("[cio] LLM allocation invalid (%s) — falling back to equal weight", reason)
            records = self._allocator.propose_equal_weight(authorized_by="cio_rule_based")

        await self._allocator.apply_allocation(records)

        # Publish agent activity for live intelligence feed
        alloc_summary = ", ".join(f"{r.pod_id}={r.new_pct:.0%}" for r in records)
        activity_msg = AgentMessage(
            timestamp=datetime.now(timezone.utc),
            sender=_AGENT_ID,
            recipient="dashboard",
            topic="agent.activity",
            payload={
                "agent_id": "cio",
                "agent_role": "CIO",
                "pod_id": "firm",
                "action": "allocation",
                "summary": f"Rebalanced: {alloc_summary}"[:200],
                "detail": f"Allocations applied. {', '.join(r.rationale for r in records)}"[:500],
            },
        )
        try:
            await self._bus.publish("agent.activity", activity_msg, publisher_id=_AGENT_ID)
        except Exception:
            pass

        logger.info("[cio] Rebalance applied: %s", {r.pod_id: r.new_pct for r in records})
        return records

    async def handle_governance_message(self, msg: AgentMessage) -> AgentMessage | None:
        """Respond to CEO/CRO messages and pod PM negotiation in loops."""
        payload = msg.payload
        action = payload.get("action", "")

        if action == "pod_pm_counter":
            # Pod PM is pushing back on a capital cut — CIO reconsiders
            pod_id = payload.get("pod_id", "")
            requested_pct = payload.get("requested_pct", None)
            current = self._allocator.get(pod_id)
            # Accept partial compromise: meet halfway
            if requested_pct is not None:
                compromise = round((current + requested_pct) / 2, 4)
                return AgentMessage(
                    timestamp=datetime.now(timezone.utc),
                    sender=_AGENT_ID,
                    recipient=msg.sender,
                    topic=msg.topic,
                    payload={
                        "consensus": True,
                        "outcome": {"pod_id": pod_id, "agreed_pct": compromise},
                        "response": f"CIO compromise: {pod_id} allocation = {compromise:.1%}",
                    },
                    correlation_id=msg.id,
                )

        if action == "ceo_strategy":
            # CEO proposes strategy direction — CIO responds with allocation plan
            return AgentMessage(
                timestamp=datetime.now(timezone.utc),
                sender=_AGENT_ID,
                recipient=msg.sender,
                topic=msg.topic,
                payload={
                    "consensus": False,  # CIO needs to propose specifics
                    "outcome": {},
                    "action": "cio_proposal",
                    "summary": f"CIO reviewing CEO strategy. Current: {self._allocator.current_allocations()}",
                },
                correlation_id=msg.id,
            )

        return None

    def _rule_based_allocation(self, pod_summaries: list[PodSummary]) -> list[AllocationRecord]:
        """Drift-correction: rebalance toward equal weight when any pod drifts >5%."""
        current = self._allocator.current_allocations()
        n = len(current)
        target = round(1.0 / n, 6)
        now = datetime.now(timezone.utc)

        needs_rebalance = any(abs(v - target) > 0.05 for v in current.values())
        if not needs_rebalance:
            # No drift — return unchanged records (same old=new)
            return [
                AllocationRecord(
                    timestamp=now, pod_id=pid,
                    old_pct=pct, new_pct=pct,
                    rationale="No rebalance needed — within drift tolerance",
                    authorized_by="cio_rule_based",
                )
                for pid, pct in current.items()
            ]

        return [
            AllocationRecord(
                timestamp=now, pod_id=pid,
                old_pct=pct, new_pct=target,
                rationale="Equal-weight drift correction",
                authorized_by="cio_rule_based",
            )
            for pid, pct in current.items()
        ]

    async def _llm_allocation(
        self,
        pod_summaries,
        ceo_narrative: str,
        cro_constraints: dict,
    ) -> list[AllocationRecord]:
        try:
            current = self._allocator.current_allocations()
            items = pod_summaries.values() if isinstance(pod_summaries, dict) else pod_summaries
            summaries_text = "\n".join(
                f"- {s.pod_id}: pnl={s.risk_metrics.daily_pnl:.2f} "
                f"dd={s.risk_metrics.drawdown_from_hwm:.3f} status={s.status}"
                for s in items
            )
            prompt = (
                "You are the CIO of an algorithmic hedge fund. "
                f"CEO narrative: {ceo_narrative}\n"
                f"Pod summaries:\n{summaries_text}\n"
                f"Current allocations: {json.dumps(current)}\n"
                f"CRO constraints: {json.dumps(cro_constraints)}\n"
                "Propose new allocations as JSON: {\"allocations\": {\"pod_id\": float, ...}}. "
                "Values must sum to 1.0. All values >= 0."
            )

            if self._session_logger:
                self._session_logger.log_reasoning("cio", "prompt", prompt)

            response_text = llm_chat(
                [{"role": "user", "content": prompt + " Respond with valid JSON only."}],
                max_tokens=300,
            )

            if self._session_logger:
                self._session_logger.log_reasoning("cio", "response", response_text)

            data = extract_json(response_text)
            new_allocs: dict[str, float] = data.get("allocations", {})
            now = datetime.now(timezone.utc)
            records = [
                AllocationRecord(
                    timestamp=now, pod_id=pid,
                    old_pct=current.get(pid, 0.0),
                    new_pct=new_allocs.get(pid, current.get(pid, 0.0)),
                    rationale="LLM-driven rebalance",
                    authorized_by="cio_llm",
                )
                for pid in current
            ]

            # Log decision after allocation records are created
            if self._session_logger:
                decision_text = (
                    f"Allocations proposed (llm=True). "
                    f"Changes: {json.dumps({r.pod_id: {'old': r.old_pct, 'new': r.new_pct} for r in records})}. "
                    f"Authorized by: cio_llm"
                )
                self._session_logger.log_reasoning("cio", "decision", decision_text)

            return records
        except Exception as exc:
            # Log the error response to close the prompt entry
            if self._session_logger:
                self._session_logger.log_reasoning("cio", "response", f"ERROR: {str(exc)}")

            logger.info("[cio] LLM allocation failed (%s) — fallback", exc)
            return self._rule_based_allocation(pod_summaries)
