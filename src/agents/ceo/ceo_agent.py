from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from src.core.bus.event_bus import EventBus
from src.core.llm import has_llm_key, llm_chat, extract_json
from src.core.models.allocation import MandateUpdate
from src.core.models.enums import EventType
from src.core.models.messages import AgentMessage
from src.core.models.pod_summary import PodSummary
from src.mission_control.session_logger import SessionLogger

logger = logging.getLogger(__name__)

_AGENT_ID = "ceo"
_DEFAULT_OBJECTIVES = [
    "Preserve capital during high-volatility regimes",
    "Achieve risk-adjusted returns above benchmark",
    "Maintain pod isolation and governance integrity",
]
_DEFAULT_CONSTRAINTS = {
    "max_firm_leverage": 1.5,
    "max_firm_drawdown": 0.15,
    "min_pods_active": 3,
}


class CEOAgent:
    """Firm-level CEO: approves mandates, sets objectives, participates in Loop 6/7.

    LLM mode: uses Qwen 3 32B via OpenRouter (falls back to OpenAI if no OpenRouter key).
    Fallback: auto-approves static mandate from defaults when no API key.
    """

    def __init__(self, bus: EventBus, session_logger: SessionLogger | None = None) -> None:
        self._bus = bus
        self._session_logger = session_logger
        self._has_llm = has_llm_key()
        self._current_mandate: MandateUpdate | None = None

    @property
    def agent_id(self) -> str:
        return _AGENT_ID

    async def approve_mandate(
        self,
        pod_summaries: list[PodSummary],
        cio_input: str = "",
        cro_constraints: dict | None = None,
    ) -> MandateUpdate:
        """Generate and approve firm mandate. Publishes MANDATE_UPDATE on bus."""
        if self._has_llm:
            mandate = await self._llm_mandate(pod_summaries, cio_input, cro_constraints or {})
        else:
            mandate = self._rule_based_mandate(pod_summaries, cro_constraints or {})

        self._current_mandate = mandate

        # Log decision if session logger is available
        if self._session_logger:
            decision_text = (
                f"Mandate approved (llm={self._has_llm}). "
                f"Narrative: {mandate.narrative}. "
                f"Constraints: {json.dumps(mandate.constraints)}. "
                f"Authorized by: {mandate.authorized_by}"
            )
            self._session_logger.log_reasoning("ceo", "decision", decision_text)

        # EventBus.publish requires an AgentMessage, not a raw dict.
        # Wrap the mandate payload in an AgentMessage from ceo to governance.
        msg = AgentMessage(
            timestamp=datetime.now(timezone.utc),
            sender=_AGENT_ID,
            recipient="governance",
            topic=f"governance.{_AGENT_ID}",
            payload={
                "event_type": EventType.MANDATE_UPDATE.value,
                "mandate": mandate.model_dump(mode="json"),
                "tags": ["mandate", "ceo"],
            },
        )
        await self._bus.publish(
            f"governance.{_AGENT_ID}",
            msg,
            publisher_id=_AGENT_ID,
        )

        # Publish agent activity for live intelligence feed
        activity_msg = AgentMessage(
            timestamp=datetime.now(timezone.utc),
            sender=_AGENT_ID,
            recipient="dashboard",
            topic="agent.activity",
            payload={
                "agent_id": "ceo",
                "agent_role": "CEO",
                "pod_id": "firm",
                "action": "mandate_update",
                "summary": (mandate.narrative or "Mandate updated")[:200],
                "detail": (mandate.rationale or "")[:500],
            },
        )
        try:
            await self._bus.publish("agent.activity", activity_msg, publisher_id=_AGENT_ID)
        except Exception:
            pass

        logger.info("[ceo] Mandate approved (llm=%s): %s", self._has_llm, mandate.narrative[:80])
        return mandate

    async def handle_governance_message(self, msg: AgentMessage, history: list[AgentMessage] | None = None) -> AgentMessage | None:
        """Respond to CIO/CRO messages in governance loops.

        Uses LLM reasoning when available, with full conversation history for context.
        Falls back to rule-based responses when no LLM key is configured.
        """
        if self._has_llm:
            try:
                return await self._llm_governance_response(msg, history)
            except Exception as exc:
                logger.warning("[ceo] LLM governance response failed (%s) — rule-based fallback", exc)

        return self._rule_based_governance_response(msg)

    def _rule_based_governance_response(self, msg: AgentMessage) -> AgentMessage | None:
        """Fallback rule-based governance handler."""
        action = msg.payload.get("action", "")

        if action in ("cio_proposal", "ceo_strategy", "cro_constraint"):
            return AgentMessage(
                timestamp=datetime.now(timezone.utc),
                sender=_AGENT_ID,
                recipient=msg.sender,
                topic=msg.topic,
                payload={
                    "consensus": True,
                    "outcome": {"action": "approve", "conditions": ["min_3_pods_active"]},
                    "response": f"CEO acknowledges {action} and approves with standard conditions.",
                },
                correlation_id=msg.id,
            )
        return None

    async def _llm_governance_response(self, msg: AgentMessage, history: list[AgentMessage] | None = None) -> AgentMessage | None:
        """LLM-powered governance deliberation with full conversation context."""
        transcript = ""
        if history:
            for h in history:
                role = h.sender.upper()
                content = h.payload.get("response") or h.payload.get("summary") or json.dumps(h.payload)
                transcript += f"[{role}]: {content}\n"

        latest_content = msg.payload.get("response") or msg.payload.get("summary") or json.dumps(msg.payload)

        system_prompt = (
            "You are the CEO of an institutional algorithmic hedge fund in a governance deliberation.\n"
            "Your priorities: preserve capital, maintain diversification, enforce risk discipline.\n"
            "You are discussing strategy with the CIO (capital allocation) and CRO (risk limits).\n\n"
            "Respond with JSON: {\"consensus\": true/false, \"response\": \"your detailed reasoning\", "
            "\"conditions\": [\"any conditions for approval\"]}\n"
            "Set consensus=true when you agree with the direction. Set consensus=false if you want "
            "to challenge or request changes. Be specific and data-driven."
        )

        user_prompt = ""
        if transcript:
            user_prompt += f"## Deliberation Transcript\n{transcript}\n\n"
        user_prompt += f"## Latest Message (from {msg.sender.upper()})\n{latest_content}\n\n"
        user_prompt += "Respond as CEO. Consider the full conversation history above."

        raw = llm_chat(
            [{"role": "system", "content": system_prompt},
             {"role": "user", "content": user_prompt}],
            max_tokens=500,
        )

        if self._session_logger:
            self._session_logger.log_reasoning("ceo", "governance_response", raw or "")

        data = extract_json(raw)
        consensus = bool(data.get("consensus", False))
        response_text = data.get("response", "CEO reviewing proposal.")
        conditions = data.get("conditions", [])

        return AgentMessage(
            timestamp=datetime.now(timezone.utc),
            sender=_AGENT_ID,
            recipient=msg.sender,
            topic=msg.topic,
            payload={
                "consensus": consensus,
                "outcome": {"action": "approve" if consensus else "challenge", "conditions": conditions},
                "response": response_text,
                "action": "ceo_response",
            },
            correlation_id=msg.id,
        )

    def _rule_based_mandate(
        self, pod_summaries, cro_constraints: dict
    ) -> MandateUpdate:
        items = pod_summaries.values() if isinstance(pod_summaries, dict) else pod_summaries
        active_pods = [s for s in items if s.status == "active"]
        narrative = (
            f"Firm operating with {len(active_pods)}/{len(list(items))} active pods. "
            "Rule-based mandate: balanced risk, preserve capital, diversified exposure."
        )
        constraints = {**_DEFAULT_CONSTRAINTS, **cro_constraints}
        return MandateUpdate(
            timestamp=datetime.now(timezone.utc),
            narrative=narrative,
            objectives=_DEFAULT_OBJECTIVES,
            constraints=constraints,
            rationale="Auto-approved: no LLM key available",
            authorized_by="ceo_rule_based",
            cio_approved=False,
            cro_approved=bool(cro_constraints),
        )

    async def _llm_mandate(
        self,
        pod_summaries,
        cio_input: str,
        cro_constraints: dict,
    ) -> MandateUpdate:
        try:
            items = pod_summaries.values() if isinstance(pod_summaries, dict) else pod_summaries
            summaries_text = "\n".join(
                f"- {s.pod_id}: status={s.status} pnl={s.risk_metrics.daily_pnl:.2f} "
                f"dd={s.risk_metrics.drawdown_from_hwm:.3f}"
                for s in items
            )
            prompt = (
                "You are the CEO of an algorithmic hedge fund. "
                f"Pod summaries:\n{summaries_text}\n"
                f"CIO input: {cio_input}\n"
                f"CRO constraints: {json.dumps(cro_constraints)}\n"
                "Generate a firm mandate as JSON with keys: "
                "narrative (str), objectives (list[str]), constraints (dict), rationale (str). "
                "Keep it concise and actionable."
            )

            if self._session_logger:
                self._session_logger.log_reasoning("ceo", "prompt", prompt)

            response_text = llm_chat(
                [{"role": "user", "content": prompt + " Respond with valid JSON only."}],
                max_tokens=400,
            )

            if self._session_logger:
                self._session_logger.log_reasoning("ceo", "response", response_text)

            data = extract_json(response_text)
            return MandateUpdate(
                timestamp=datetime.now(timezone.utc),
                narrative=data.get("narrative", "LLM mandate"),
                objectives=data.get("objectives", _DEFAULT_OBJECTIVES),
                constraints={**_DEFAULT_CONSTRAINTS, **data.get("constraints", {}), **cro_constraints},
                rationale=data.get("rationale", "LLM-generated"),
                authorized_by="ceo_llm",
                cio_approved=bool(cio_input),
                cro_approved=bool(cro_constraints),
            )
        except Exception as exc:
            # Log the error response to close the prompt entry
            if self._session_logger:
                self._session_logger.log_reasoning("ceo", "response", f"ERROR: {str(exc)}")

            logger.info("[ceo] LLM mandate failed (%s) — fallback", exc)
            return self._rule_based_mandate(pod_summaries, cro_constraints)
