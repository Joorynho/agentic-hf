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
        self._pod_intelligence: dict[str, dict] = {}

    def set_pod_intelligence(self, pod_briefs: dict[str, dict]) -> None:
        """Inject per-pod intelligence briefs for governance reasoning.

        Called by SessionManager before governance cycles. Each brief contains
        macro_regime, top_signals, key_positions, and fred_highlights.
        """
        self._pod_intelligence = pod_briefs

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

    async def handle_governance_message(self, msg: AgentMessage, history: list[AgentMessage] | None = None) -> AgentMessage | None:
        """Respond to CEO/CRO messages and pod PM negotiation in loops.

        Uses LLM reasoning when available, with full conversation history.
        Falls back to rule-based responses when no LLM key is configured.
        """
        if self._has_llm:
            try:
                return await self._llm_governance_response(msg, history)
            except Exception as exc:
                logger.warning("[cio] LLM governance response failed (%s) — rule-based fallback", exc)

        return self._rule_based_governance_response(msg)

    def _rule_based_governance_response(self, msg: AgentMessage) -> AgentMessage | None:
        """Fallback rule-based governance handler."""
        action = msg.payload.get("action", "")

        if action == "pod_pm_counter":
            pod_id = msg.payload.get("pod_id", "")
            requested_pct = msg.payload.get("requested_pct", None)
            current = self._allocator.get(pod_id)
            if requested_pct is not None:
                compromise = round((current + requested_pct) / 2, 4)
                return AgentMessage(
                    timestamp=datetime.now(timezone.utc),
                    sender=_AGENT_ID, recipient=msg.sender, topic=msg.topic,
                    payload={"consensus": True, "outcome": {"pod_id": pod_id, "agreed_pct": compromise},
                             "response": f"CIO compromise: {pod_id} = {compromise:.1%}"},
                    correlation_id=msg.id,
                )

        if action in ("ceo_strategy", "cio_proposal", "cro_constraint"):
            return AgentMessage(
                timestamp=datetime.now(timezone.utc),
                sender=_AGENT_ID, recipient=msg.sender, topic=msg.topic,
                payload={"consensus": False, "outcome": {}, "action": "cio_proposal",
                         "response": f"CIO reviewing. Current allocations: {self._allocator.current_allocations()}"},
                correlation_id=msg.id,
            )
        return None

    def _format_intelligence_brief(self) -> str:
        """Format pod intelligence briefs for LLM context."""
        if not self._pod_intelligence:
            return ""
        lines = ["## Pod Intelligence Briefs"]
        for pod_id, brief in self._pod_intelligence.items():
            lines.append(f"\n### {pod_id.upper()}")
            if brief.get("macro_regime"):
                lines.append(f"  Macro regime: {brief['macro_regime']}")
            if brief.get("top_signals"):
                signals = brief["top_signals"][:5]
                lines.append(f"  Top signals: {', '.join(str(s) for s in signals)}")
            if brief.get("key_positions"):
                for pos in brief["key_positions"][:5]:
                    lines.append(f"  Position: {pos}")
            if brief.get("fred_highlights"):
                lines.append(f"  FRED: {brief['fred_highlights']}")
            if brief.get("cross_pod_conflicts"):
                for conflict in brief["cross_pod_conflicts"]:
                    lines.append(f"  WARNING: {conflict}")
        return "\n".join(lines)

    async def _llm_governance_response(self, msg: AgentMessage, history: list[AgentMessage] | None = None) -> AgentMessage | None:
        """LLM-powered governance deliberation with intelligence context."""
        transcript = ""
        if history:
            for h in history:
                role = h.sender.upper()
                content = h.payload.get("response") or h.payload.get("summary") or json.dumps(h.payload)
                transcript += f"[{role}]: {content}\n"

        latest_content = msg.payload.get("response") or msg.payload.get("summary") or json.dumps(msg.payload)
        intel_brief = self._format_intelligence_brief()
        current_allocs = json.dumps(self._allocator.current_allocations())

        system_prompt = (
            "You are the CIO of an institutional algorithmic hedge fund in a governance deliberation.\n"
            "Your focus: capital allocation across pods, risk-adjusted returns, portfolio construction.\n"
            "You work with the CEO (strategy/mandate) and CRO (risk constraints).\n\n"
            "Respond with JSON: {\"consensus\": true/false, \"response\": \"your detailed reasoning\", "
            "\"proposed_allocations\": {\"pod_id\": pct, ...} or null}\n"
            "Set consensus=true when you agree. Set consensus=false to propose changes.\n"
            "Reference specific pod data and signals when justifying allocation shifts."
        )

        user_prompt = f"## Current Allocations\n{current_allocs}\n\n"
        if intel_brief:
            user_prompt += f"{intel_brief}\n\n"
        if transcript:
            user_prompt += f"## Deliberation Transcript\n{transcript}\n\n"
        user_prompt += f"## Latest Message (from {msg.sender.upper()})\n{latest_content}\n\n"
        user_prompt += "Respond as CIO with your allocation reasoning."

        raw = llm_chat(
            [{"role": "system", "content": system_prompt},
             {"role": "user", "content": user_prompt}],
            max_tokens=600,
        )

        if self._session_logger:
            self._session_logger.log_reasoning("cio", "governance_response", raw or "")

        data = extract_json(raw)
        consensus = bool(data.get("consensus", False))
        response_text = data.get("response", "CIO reviewing proposal.")
        proposed = data.get("proposed_allocations")

        payload = {
            "consensus": consensus,
            "outcome": {"action": "cio_proposal" if not consensus else "cio_approved"},
            "response": response_text,
            "action": "cio_proposal",
        }
        if proposed and isinstance(proposed, dict):
            payload["proposed_allocations"] = proposed

        return AgentMessage(
            timestamp=datetime.now(timezone.utc),
            sender=_AGENT_ID, recipient=msg.sender, topic=msg.topic,
            payload=payload, correlation_id=msg.id,
        )

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
            intel_brief = self._format_intelligence_brief()
            prompt = (
                "You are the CIO of an algorithmic hedge fund. "
                f"CEO narrative: {ceo_narrative}\n"
                f"Pod summaries:\n{summaries_text}\n"
                f"Current allocations: {json.dumps(current)}\n"
                f"CRO constraints: {json.dumps(cro_constraints)}\n"
            )
            if intel_brief:
                prompt += f"\n{intel_brief}\n\n"
            prompt += (
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
