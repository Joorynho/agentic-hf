from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from src.core.llm import extract_json, has_llm_key, llm_chat
from src.core.models.execution import SpecialistBrief, SpecialistRequest

logger = logging.getLogger(__name__)

MAX_SPECIALIST_REQUESTS = 3
SPECIALIST_TIMEOUT_SECONDS = 18


def _brief_id(pod_id: str, req: SpecialistRequest) -> str:
    raw = f"{pod_id}|{req.type}|{req.symbol}|{req.question}|{datetime.now(timezone.utc).isoformat()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:18]


def _context_excerpt(context: dict[str, Any]) -> str:
    features = context.get("features") or {}
    sizing = context.get("sizing_context") or {}
    bits = [
        f"macro_outlook={features.get('macro_outlook') or features.get('liquidity_outlook') or 'unknown'}",
        f"regime={(features.get('regime') or {}).get('label', 'unknown') if isinstance(features.get('regime'), dict) else features.get('regime', 'unknown')}",
        f"pod_nav={sizing.get('pod_nav', 'unknown')}",
        f"cash={sizing.get('available_cash', 'unknown')}",
    ]
    catalysts = context.get("foresight_events") or features.get("foresight_events") or []
    if catalysts:
        bits.append("top_catalysts=" + "; ".join(
            str(c.get("title", ""))[:120] for c in catalysts[:5] if isinstance(c, dict)
        ))
    return "\n".join(bits)


class SpecialistRunner:
    """Runs bounded advisory analyst briefs requested by a PM."""

    def __init__(self, max_requests: int = MAX_SPECIALIST_REQUESTS, timeout_seconds: int = SPECIALIST_TIMEOUT_SECONDS) -> None:
        self.max_requests = max_requests
        self.timeout_seconds = timeout_seconds

    async def run_requests(
        self,
        *,
        pod_id: str,
        requests: list[dict] | list[SpecialistRequest] | None,
        context: dict,
    ) -> list[dict]:
        validated: list[SpecialistRequest] = []
        for raw in requests or []:
            try:
                req = raw if isinstance(raw, SpecialistRequest) else SpecialistRequest.model_validate(raw)
            except ValidationError as exc:
                logger.info("[specialist] Ignoring invalid specialist request for %s: %s", pod_id, exc)
                continue
            validated.append(req)
            if len(validated) >= self.max_requests:
                break

        briefs: list[dict] = []
        for req in validated:
            brief = await self._run_one(pod_id=pod_id, req=req, context=context)
            briefs.append(brief.model_dump(mode="json"))
        return briefs

    async def _run_one(self, *, pod_id: str, req: SpecialistRequest, context: dict) -> SpecialistBrief:
        fallback = self._fallback_brief(pod_id, req, context)
        if not has_llm_key():
            return fallback

        prompt = f"""You are a specialist analyst supporting a trading PM.

Pod: {pod_id}
Specialist type: {req.type}
Symbol: {req.symbol or 'portfolio-level'}
Question: {req.question}
Why requested: {req.reason}
Related catalysts: {', '.join(req.related_catalyst_ids) or 'none'}
Decision impact: {req.decision_impact or 'not specified'}
Required data: {req.required_data or 'not specified'}

Current context:
{_context_excerpt(context)}

Return ONLY JSON:
{{
  "conclusion": "one concise conclusion",
  "supporting_evidence": ["specific evidence point"],
  "opposing_evidence": ["specific counterpoint"],
  "data_used": ["data source or metric actually used"],
  "missing_data": ["important data not available"],
  "decision_impact": "how this should change the PM decision",
  "confidence": 0.0,
  "invalidation": "what would prove this wrong",
  "source_refs": []
}}"""
        try:
            raw = await asyncio.wait_for(
                asyncio.to_thread(
                    llm_chat,
                    [{"role": "user", "content": prompt}],
                    700,
                    "research",
                ),
                timeout=self.timeout_seconds,
            )
            data = extract_json(raw)
            return SpecialistBrief(
                brief_id=_brief_id(pod_id, req),
                type=req.type,
                symbol=req.symbol,
                question=req.question,
                conclusion=str(data.get("conclusion") or fallback.conclusion)[:1000],
                supporting_evidence=[str(x)[:500] for x in data.get("supporting_evidence", [])[:6]],
                opposing_evidence=[str(x)[:500] for x in data.get("opposing_evidence", [])[:6]],
                data_used=[str(x)[:260] for x in data.get("data_used", [])[:8]],
                missing_data=[str(x)[:260] for x in data.get("missing_data", [])[:8]],
                decision_impact=str(data.get("decision_impact") or req.decision_impact or "")[:700],
                related_catalyst_ids=list(req.related_catalyst_ids or []),
                confidence=float(data.get("confidence", fallback.confidence) or fallback.confidence),
                invalidation=str(data.get("invalidation") or fallback.invalidation)[:800],
                source_refs=list(data.get("source_refs") or []),
            )
        except Exception as exc:
            logger.info("[specialist] %s/%s brief fallback: %s", pod_id, req.type, exc)
            return fallback

    @staticmethod
    def _fallback_brief(pod_id: str, req: SpecialistRequest, context: dict) -> SpecialistBrief:
        catalysts = context.get("foresight_events") or (context.get("features") or {}).get("foresight_events") or []
        catalyst_titles = [
            str(c.get("title", ""))[:160]
            for c in catalysts
            if isinstance(c, dict) and (not req.related_catalyst_ids or c.get("event_id") in req.related_catalyst_ids)
        ][:3]
        support = catalyst_titles or ["No specialist LLM output available; use existing PM evidence and hard gates."]
        return SpecialistBrief(
            brief_id=_brief_id(pod_id, req),
            type=req.type,
            symbol=req.symbol,
            question=req.question,
            conclusion=(
                f"{req.type} fallback brief for {req.symbol or pod_id}: "
                "treat this as advisory and require the PM thesis to cite concrete evidence."
            ),
            supporting_evidence=support,
            opposing_evidence=["Fallback brief cannot independently verify the PM view."],
            related_catalyst_ids=list(req.related_catalyst_ids or []),
            data_used=["Foresight catalyst ledger", "Current PM context"],
            missing_data=[req.required_data] if req.required_data else ["Specialist LLM/web verification unavailable"],
            decision_impact=req.decision_impact or "Use this as a caution flag; do not add risk unless the PM thesis supplies concrete evidence.",
            confidence=0.35,
            invalidation="If current data contradicts the PM thesis, HOLD or reduce risk.",
            source_refs=[],
        )
