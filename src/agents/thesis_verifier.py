"""Generator-Verifier pattern for PM trade decisions.

After the PM generates a TradeProposal, the ThesisVerifier evaluates
reasoning quality.  Weak reasoning triggers a revision request (max 2 rounds).

Rule-based evaluation always runs; LLM evaluation is added when an API key
is available, blended 40/60 with the rule-based score.
"""
from __future__ import annotations

import json
import logging

from src.core.models.execution import VerificationResult

logger = logging.getLogger(__name__)

# Phrases that signal substance — at least one must appear for a BUY/SELL
_SIGNAL_KEYWORDS = [
    "vix", "fed", "fred", "yield", "rate", "inflation", "gdp", "cpi",
    "price", "polymarket", "probability", "sentiment", "sector",
    "earnings", "qqq", "spy", "spx", "momentum", "trend", "breakout",
    "support", "resistance", "volume", "rsi", "macd", "moving average",
    "interest rate", "credit spread", "dxy", "bitcoin", "btc", "eth",
    "oil", "gold", "silver", "copper", "natural gas",
]

# Phrases that indicate weak, generic reasoning
_WEAK_PHRASES = [
    "positive macro", "negative macro", "macro conditions",
    "good opportunity", "market looks", "seems bullish", "seems bearish",
    "generally positive", "generally negative", "overall positive",
]

# Minimum useful reasoning length for a non-HOLD decision
_MIN_REASONING_LEN = 60


class ThesisVerifier:
    """Evaluates PM trade reasoning quality and returns actionable feedback."""

    def verify(self, pm_decision: dict, asset_class: str = "") -> VerificationResult:
        """Rule-based quality check — always available, no API key needed."""
        trades = pm_decision.get("trades", [])
        reasoning = pm_decision.get("reasoning", "")

        # No-trade decisions don't need deep reasoning
        active_trades = [t for t in trades if str(t.get("action", "HOLD")).upper() != "HOLD"]
        if not active_trades:
            return VerificationResult(passed=True, quality_score=1.0)

        score = 1.0
        issues: list[str] = []
        reasoning_lower = reasoning.lower()

        if not reasoning or len(reasoning) < _MIN_REASONING_LEN:
            issues.append(f"reasoning is too brief ({len(reasoning)} chars — aim for 80+)")
            score -= 0.35

        if not any(kw in reasoning_lower for kw in _SIGNAL_KEYWORDS):
            issues.append("reasoning references no data signals (FRED, prices, Polymarket odds, etc.)")
            score -= 0.30

        generic_count = sum(1 for p in _WEAK_PHRASES if p in reasoning_lower)
        if generic_count >= 2:
            issues.append("reasoning relies on generic macro phrases without a specific catalyst")
            score -= 0.20

        for t in active_trades:
            conv = float(t.get("conviction", 0.5))
            if conv == 0.5:
                issues.append(
                    f"conviction for {t.get('symbol', '?')} is the default 0.5 — set it explicitly"
                )
                score -= 0.10
            elif conv < 0.15:
                issues.append(f"conviction {conv:.2f} for {t.get('symbol', '?')} is extremely low")
                score -= 0.05

        score = max(0.0, min(1.0, score))
        passed = score >= 0.5 and len(issues) <= 1

        feedback = ""
        if issues:
            feedback = (
                "Reasoning quality issues:\n"
                + "\n".join(f"  • {i}" for i in issues)
                + "\n\nRevise by: citing at least one specific data point (e.g. VIX=18, "
                "10Y yield at 4.5%, Polymarket 65% probability), naming a concrete catalyst, "
                "and explaining why this exact instrument is the best vehicle. "
                "If evidence is insufficient, HOLD instead."
            )

        return VerificationResult(passed=passed, quality_score=score, feedback=feedback)

    async def verify_with_llm(
        self, pm_decision: dict, asset_class: str = ""
    ) -> VerificationResult:
        """Rule-based evaluation + optional LLM scoring (blended 40/60).

        Falls back to rule-based if no API key or LLM call fails.
        """
        rule_result = self.verify(pm_decision, asset_class)

        # Only spend an LLM call when rule-based already found issues
        if rule_result.passed:
            return rule_result

        try:
            from src.core.llm import has_llm_key, llm_chat

            if not has_llm_key():
                return rule_result

            active_trades = [
                t for t in pm_decision.get("trades", [])
                if str(t.get("action", "HOLD")).upper() != "HOLD"
            ]
            trades_summary = ", ".join(
                f"{t.get('action')} {t.get('qty')} {t.get('symbol')}"
                for t in active_trades
            )
            reasoning_snippet = (pm_decision.get("reasoning") or "")[:400]

            prompt = (
                f"You are auditing a {asset_class} PM's trade reasoning quality.\n"
                f"Proposed trades: {trades_summary}\n"
                f"Reasoning: {reasoning_snippet}\n\n"
                f"Rule-based issues already identified:\n{rule_result.feedback}\n\n"
                f"Score reasoning quality 0–1:\n"
                f"  0.0 = completely generic, no specific signals cited\n"
                f"  0.5 = some signals mentioned but catalyst unclear\n"
                f"  1.0 = specific, verifiable data + clear catalyst + right instrument\n\n"
                f"Respond with JSON only: "
                f'{{\"quality_score\": 0.6, \"feedback\": \"one specific improvement\"}}'
            )

            resp = llm_chat([{"role": "user", "content": prompt}], max_tokens=150)
            start = resp.find("{")
            end = resp.rfind("}") + 1
            if start >= 0 and end > start:
                parsed = json.loads(resp[start:end])
                llm_score = float(parsed.get("quality_score", rule_result.quality_score))
                llm_feedback = parsed.get("feedback", "").strip()
                blended = 0.4 * rule_result.quality_score + 0.6 * llm_score
                feedback = llm_feedback or rule_result.feedback
                return VerificationResult(
                    passed=blended >= 0.5,
                    quality_score=round(blended, 3),
                    feedback=feedback,
                )
        except Exception as e:
            logger.debug("[thesis_verifier] LLM evaluation skipped: %s", e)

        return rule_result
