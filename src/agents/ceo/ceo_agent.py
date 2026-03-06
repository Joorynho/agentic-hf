from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

from src.core.bus.event_bus import EventBus
from src.core.models.allocation import MandateUpdate
from src.core.models.enums import EventType
from src.core.models.messages import AgentMessage, Event
from src.core.models.pod_summary import PodSummary

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

    LLM mode: uses gpt-4o-mini to generate narrative + approve mandate.
    Fallback: auto-approves static mandate from defaults when no API key.
    """

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._api_key = os.getenv("OPENAI_API_KEY", "")
        self._has_llm = bool(self._api_key)
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
        logger.info("[ceo] Mandate approved (llm=%s): %s", self._has_llm, mandate.narrative[:80])
        return mandate

    async def handle_governance_message(self, msg: AgentMessage) -> AgentMessage | None:
        """Respond to CIO/CRO messages in collaboration loops."""
        payload = msg.payload
        action = payload.get("action", "")

        if action == "cio_proposal":
            # CEO reviews CIO capital proposal and accepts or counter-proposes
            response_text = (
                f"CEO reviewing CIO proposal: {payload.get('summary', '')}. "
                "Accepted with condition: maintain minimum 3 active pods."
            )
            return AgentMessage(
                timestamp=datetime.now(timezone.utc),
                sender=_AGENT_ID,
                recipient=msg.sender,
                topic=msg.topic,
                payload={
                    "consensus": True,
                    "outcome": {"action": "approve", "conditions": ["min_3_pods_active"]},
                    "response": response_text,
                },
                correlation_id=msg.id,
            )

        if action == "cro_constraint":
            # CEO acknowledges CRO risk constraint
            return AgentMessage(
                timestamp=datetime.now(timezone.utc),
                sender=_AGENT_ID,
                recipient=msg.sender,
                topic=msg.topic,
                payload={
                    "consensus": True,
                    "outcome": {"action": "acknowledge_constraint"},
                    "response": "CEO acknowledges CRO constraint and will update mandate.",
                },
                correlation_id=msg.id,
            )

        return None

    def _rule_based_mandate(
        self, pod_summaries: list[PodSummary], cro_constraints: dict
    ) -> MandateUpdate:
        active_pods = [s for s in pod_summaries if s.status == "active"]
        narrative = (
            f"Firm operating with {len(active_pods)}/{len(pod_summaries)} active pods. "
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
        pod_summaries: list[PodSummary],
        cio_input: str,
        cro_constraints: dict,
    ) -> MandateUpdate:
        try:
            import openai

            summaries_text = "\n".join(
                f"- {s.pod_id}: status={s.status} pnl={s.risk_metrics.daily_pnl:.2f} "
                f"dd={s.risk_metrics.drawdown_from_hwm:.3f}"
                for s in pod_summaries
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
            client = openai.OpenAI(api_key=self._api_key)
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=400,
                response_format={"type": "json_object"},
                messages=[{"role": "user", "content": prompt + " Respond with valid JSON only."}],
            )
            data = json.loads(resp.choices[0].message.content)
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
            logger.info("[ceo] LLM mandate failed (%s) — fallback", exc)
            return self._rule_based_mandate(pod_summaries, cro_constraints)
