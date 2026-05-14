from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from src.core.llm import extract_json, has_llm_key, llm_chat
from src.core.models.execution import CommitteeReview, Order


REVIEW_TIMEOUT_SECONDS = 20


def _review_id(pod_id: str, symbol: str, side: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    return f"ic:{pod_id}:{symbol}:{side}:{ts}"


def _position_qty(accountant, symbol: str) -> float:
    if not accountant:
        return 0.0
    try:
        pos = accountant.current_positions.get(symbol)
        if pos is None:
            return 0.0
        qty = getattr(pos, "qty", None)
        if qty is None:
            qty = getattr(pos, "quantity", 0.0)
        return float(qty or 0.0)
    except Exception:
        return 0.0


def _estimate_price(accountant, symbol: str, fallback: float = 100.0) -> float:
    if accountant:
        try:
            price = float(accountant.get_last_price(symbol, 0.0) or 0.0)
            if price > 0:
                return price
        except Exception:
            pass
        try:
            pos = accountant.current_positions.get(symbol)
            price = float(getattr(pos, "current_price", 0.0) or 0.0) if pos is not None else 0.0
            if price > 0:
                return price
        except Exception:
            pass
    return fallback


class InvestmentCommitteeReviewer:
    """Reasoning gate before risk/execution.

    The IC is advisory and pre-hard-control only. It can block or ask for one
    PM revision, but it never replaces rule-based risk limits.
    """

    def should_review(
        self,
        *,
        order: Order,
        accountant,
        matching_trade: dict | None = None,
        pm_decision: dict | None = None,
        thesis_gate_result: dict | None = None,
        quality_gate: dict | None = None,
        notional_threshold_pct: float = 0.10,
    ) -> tuple[bool, list[str]]:
        matching_trade = matching_trade or {}
        pm_decision = pm_decision or {}
        thesis_gate_result = thesis_gate_result or {}
        quality_gate = quality_gate or {}

        if not self._order_increases_risk(order, accountant):
            return False, []

        triggers: list[str] = []
        existing_qty = _position_qty(accountant, order.symbol)
        side = order.side.value.upper()
        if existing_qty == 0 and side == "BUY":
            triggers.append("new_entry")
        elif existing_qty > 0 and side == "BUY":
            triggers.append("position_expansion")
        elif existing_qty < 0 and side == "SELL":
            triggers.append("position_expansion")

        conviction = float(getattr(order, "conviction", 0.5) or matching_trade.get("conviction") or 0.5)
        if conviction >= 0.75:
            triggers.append("high_conviction")

        score = float(thesis_gate_result.get("quality_score", 1.0) or 0.0)
        if score < 0.70 or quality_gate.get("action") in {"warn", "block"}:
            triggers.append("weak_or_stale_evidence")

        nav = float(getattr(accountant, "nav", 0.0) or 0.0) if accountant else 0.0
        price = _estimate_price(accountant, order.symbol)
        notional = abs(float(order.quantity or 0.0) * price)
        if nav > 0 and notional >= nav * notional_threshold_pct:
            triggers.append("large_notional")

        return bool(triggers), triggers

    async def review(
        self,
        *,
        pod_id: str,
        order: Order,
        accountant,
        matching_trade: dict | None,
        pm_decision: dict | None,
        trade_reasoning: str,
        thesis_gate_result: dict | None,
        quality_gate: dict | None,
        ctx: dict | None = None,
        triggers: list[str] | None = None,
    ) -> CommitteeReview:
        triggers = triggers or []
        if not has_llm_key():
            return self._fallback_review(
                pod_id=pod_id,
                order=order,
                accountant=accountant,
                trade_reasoning=trade_reasoning,
                thesis_gate_result=thesis_gate_result or {},
                quality_gate=quality_gate or {},
                triggers=triggers,
            )

        prompt = self._prompt(
            pod_id=pod_id,
            order=order,
            accountant=accountant,
            matching_trade=matching_trade or {},
            pm_decision=pm_decision or {},
            trade_reasoning=trade_reasoning,
            thesis_gate_result=thesis_gate_result or {},
            quality_gate=quality_gate or {},
            ctx=ctx or {},
            triggers=triggers,
        )
        try:
            raw = await asyncio.wait_for(
                asyncio.to_thread(
                    llm_chat,
                    [
                        {
                            "role": "system",
                            "content": (
                                "You are an investment committee challenge panel. "
                                "You review only risk-increasing trades. Be strict on weak evidence, "
                                "stale catalysts, bad instrument fit, and crowded/chasing setups. "
                                "Do not replace hard risk limits."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    900,
                    "thesis_verification",
                ),
                timeout=REVIEW_TIMEOUT_SECONDS,
            )
            data = extract_json(raw)
            decision = str(data.get("decision") or "APPROVE").upper()
            if decision not in {"APPROVE", "REVISE", "REJECT"}:
                decision = "APPROVE"
            reviewers = data.get("reviewers") if isinstance(data.get("reviewers"), list) else []
            reviewer_votes = data.get("reviewer_votes") if isinstance(data.get("reviewer_votes"), list) else reviewers
            blockers = data.get("blockers") if isinstance(data.get("blockers"), list) else []
            revision_fields = data.get("revision_fields") if isinstance(data.get("revision_fields"), list) else []
            return CommitteeReview(
                review_id=_review_id(pod_id, order.symbol, order.side.value.upper()),
                pod_id=pod_id,
                symbol=order.symbol,
                side=order.side.value.upper(),
                decision=decision,  # type: ignore[arg-type]
                reason=str(data.get("reason") or data.get("feedback") or "")[:1200],
                reviewers=reviewers[:8],
                reviewer_votes=reviewer_votes[:8],
                blockers=[str(x)[:220] for x in blockers[:8]],
                revision_fields=[str(x)[:80] for x in revision_fields[:8]],
                confidence=float(data.get("confidence") or 0.65),
            )
        except Exception as exc:
            review = self._fallback_review(
                pod_id=pod_id,
                order=order,
                accountant=accountant,
                trade_reasoning=trade_reasoning,
                thesis_gate_result=thesis_gate_result or {},
                quality_gate=quality_gate or {},
                triggers=triggers,
            )
            review.reason = f"IC LLM unavailable; fallback review used. {review.reason} ({exc})"
            return review

    def _fallback_review(
        self,
        *,
        pod_id: str,
        order: Order,
        accountant,
        trade_reasoning: str,
        thesis_gate_result: dict,
        quality_gate: dict,
        triggers: list[str],
    ) -> CommitteeReview:
        score = float(thesis_gate_result.get("quality_score", 1.0) or 0.0)
        reason = str(quality_gate.get("reason") or thesis_gate_result.get("feedback") or "")
        decision = "APPROVE"
        if score < 0.35 or quality_gate.get("action") == "block":
            decision = "REJECT"
        elif score < 0.70 or quality_gate.get("action") == "warn":
            decision = "REVISE"
        if not str(trade_reasoning or "").strip() and self._order_increases_risk(order, accountant):
            decision = "REJECT"
            reason = "No PM thesis captured for risk-increasing trade."
        return CommitteeReview(
            review_id=_review_id(pod_id, order.symbol, order.side.value.upper()),
            pod_id=pod_id,
            symbol=order.symbol,
            side=order.side.value.upper(),
            decision=decision,  # type: ignore[arg-type]
            reason=(
                reason
                or f"Fallback IC review based on triggers: {', '.join(triggers) or 'risk_increasing'}."
            )[:1200],
            reviewers=[
                {"role": "risk_skeptic", "view": "checked downside and sizing", "vote": decision},
                {"role": "trend_technical", "view": "requires PM evidence of non-chasing entry", "vote": decision},
                {"role": "asset_specific_reviewer", "view": "requires asset-specific evidence and instrument fit", "vote": decision},
                {"role": "thesis_quality_reviewer", "view": "checked thesis verifier and catalyst linkage", "vote": decision},
            ],
            reviewer_votes=[
                {"role": "risk_skeptic", "vote": decision, "reason": "fallback sizing/downside check"},
                {"role": "trend_technical", "vote": decision, "reason": "fallback entry-quality check"},
                {"role": "asset_specific_reviewer", "vote": decision, "reason": "fallback instrument-fit check"},
                {"role": "thesis_quality_reviewer", "vote": decision, "reason": "fallback thesis-quality check"},
            ],
            blockers=[reason] if decision == "REJECT" and reason else [],
            revision_fields=self._revision_fields_from_reason(reason, score) if decision == "REVISE" else [],
            confidence=0.60,
        )

    @staticmethod
    def _order_increases_risk(order: Order, accountant) -> bool:
        existing_qty = _position_qty(accountant, order.symbol)
        side = order.side.value.upper()
        qty = abs(float(order.quantity or 0.0))
        if existing_qty > 0:
            return side == "BUY" or (side == "SELL" and qty > abs(existing_qty))
        if existing_qty < 0:
            return side == "SELL" or (side == "BUY" and qty > abs(existing_qty))
        return True

    def _prompt(
        self,
        *,
        pod_id: str,
        order: Order,
        accountant,
        matching_trade: dict,
        pm_decision: dict,
        trade_reasoning: str,
        thesis_gate_result: dict,
        quality_gate: dict,
        ctx: dict,
        triggers: list[str],
    ) -> str:
        features = ctx.get("features") or {}
        catalysts = ctx.get("foresight_events") or features.get("foresight_events") or []
        specialists = ctx.get("specialist_briefs") or features.get("specialist_briefs") or []
        nav = float(getattr(accountant, "nav", 0.0) or 0.0) if accountant else 0.0
        price = _estimate_price(accountant, order.symbol)
        notional = abs(float(order.quantity or 0.0) * price)
        return (
            f"Pod: {pod_id}\n"
            f"Order: {order.side.value.upper()} {order.quantity} {order.symbol} "
            f"(est notional ${notional:,.2f}, nav ${nav:,.2f})\n"
            f"Triggers: {', '.join(triggers) or 'risk-increasing'}\n"
            f"PM trade: {matching_trade}\n"
            f"PM decision catalyst_ids: {pm_decision.get('catalyst_ids') or matching_trade.get('catalyst_ids')}\n"
            f"PM catalyst reasoning: {pm_decision.get('catalyst_reasoning') or matching_trade.get('catalyst_reasoning')}\n"
            f"PM thesis: {trade_reasoning[:2200]}\n"
            f"Thesis verifier: {thesis_gate_result}\n"
            f"Quality gate: {quality_gate}\n"
            f"Top catalysts: {catalysts[:6]}\n"
            f"Specialist briefs: {specialists[:6]}\n\n"
            "Return ONLY JSON:\n"
            '{"decision":"APPROVE|REVISE|REJECT","reason":"specific feedback",'
            '"confidence":0.0,"blockers":["hard reasoning blocker"],'
            '"revision_fields":["weak_facts|stale_data|catalyst_linkage|sizing|invalidation|market_regime"],'
            '"reviewer_votes":[{"role":"risk_skeptic","vote":"APPROVE|REVISE|REJECT","reason":"..."},'
            '{"role":"trend_technical","vote":"APPROVE|REVISE|REJECT","reason":"..."},'
            '{"role":"asset_specific_reviewer","vote":"APPROVE|REVISE|REJECT","reason":"..."},'
            '{"role":"thesis_quality_reviewer","vote":"APPROVE|REVISE|REJECT","reason":"..."}],'
            '"reviewers":[{"role":"risk_skeptic","view":"..."},'
            '{"role":"trend_technical","view":"..."},{"role":"asset_specific_reviewer","view":"..."},'
            '{"role":"thesis_quality_reviewer","view":"..."}]}\n'
            "APPROVE only if the trade is supported enough to proceed to hard risk gates. "
            "REVISE if one PM retry could fix missing catalyst/evidence/instrument-fit detail. "
            "REJECT if the trade should not add risk."
        )

    @staticmethod
    def _revision_fields_from_reason(reason: str, score: float) -> list[str]:
        text = str(reason or "").lower()
        fields: list[str] = []
        if any(word in text for word in ("fact", "evidence", "data")):
            fields.append("weak_facts")
        if any(word in text for word in ("stale", "old", "current")):
            fields.append("stale_data")
        if any(word in text for word in ("catalyst", "why now")):
            fields.append("catalyst_linkage")
        if any(word in text for word in ("size", "notional", "risk")):
            fields.append("sizing")
        if any(word in text for word in ("invalidation", "stop", "exit")):
            fields.append("invalidation")
        if any(word in text for word in ("regime", "rates", "dollar", "inflation")):
            fields.append("market_regime")
        if not fields and score < 0.70:
            fields.append("weak_facts")
        return fields[:6]
