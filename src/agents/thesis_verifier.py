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
from src.core.thesis_lifecycle import infer_asset_profile, profile_coverage
from src.core.thesis_quality import asset_evidence_checklist

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

_REQUIRED_REASONING_LABELS = ("thesis:", "entry:", "invalidation:", "risk:")
_EVIDENCE_REASONING_LABELS: dict[str, tuple[str, ...]] = {
    "facts": ("facts:", "verified facts:", "data facts:"),
    "assumptions": ("assumptions:", "unproven assumptions:"),
    "valuation/evidence": ("valuation/evidence:", "evidence:", "valuation:", "relative value:"),
    "why now": ("why now:", "why-now:", "timing:", "catalyst window:"),
    "timeframe": ("timeframe:", "holding period:", "max_hold_days", "hold period:"),
}
_PRECIOUS_METALS_SYMBOLS = {"GLD", "GDX", "GDXJ", "SLV", "IAU", "SGOL", "SIL", "SILJ", "PAXG"}

_VALUATION_CLAIM_TERMS = (
    "undervalued",
    "overvalued",
    "cheap",
    "expensive",
    "discount",
    "mispriced",
    "underpriced",
    "relative value",
)

_VALUATION_EVIDENCE_TERMS: dict[str, tuple[str, ...]] = {
    "crypto": (
        "tvl",
        "fdv",
        "market cap",
        "mcap",
        "protocol fees",
        "fee revenue",
        "revenue",
        "stablecoin",
        "dex volume",
        "active address",
        "active user",
        "transaction",
        "open interest",
        "funding",
        "relative performance",
    ),
    "equities": (
        "p/e",
        "multiple",
        "ev/",
        "ebitda",
        "sales",
        "earnings",
        "eps",
        "revenue",
        "margin",
        "peer",
        "estimate",
        "cash flow",
        "free cash flow",
    ),
    "fx": (
        "rate differential",
        "carry",
        "yield differential",
        "real yield",
        "current account",
        "purchasing power",
        "terms of trade",
        "positioning",
    ),
    "commodities": (
        "inventory",
        "inventories",
        "stockpile",
        "curve",
        "contango",
        "backwardation",
        "supply",
        "demand",
        "production",
        "consumption",
        "positioning",
        "flows",
        "real yield",
        "usd",
    ),
}

# Minimum useful reasoning length for a non-HOLD decision
_MIN_REASONING_LEN = 60


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _missing_evidence_labels(text: str) -> list[str]:
    missing: list[str] = []
    for name, needles in _EVIDENCE_REASONING_LABELS.items():
        if not _contains_any(text, needles):
            missing.append(name)
    return missing


def _valuation_evidence_terms(asset_class: str) -> tuple[str, ...]:
    key = str(asset_class or "").strip().lower()
    if key not in _VALUATION_EVIDENCE_TERMS:
        key = "commodities" if "commod" in key else key
    return _VALUATION_EVIDENCE_TERMS.get(key, _VALUATION_EVIDENCE_TERMS["equities"])


def _claim_quality_issues(reasoning_lower: str, asset_class: str) -> list[str]:
    issues: list[str] = []
    asset_key = str(asset_class or "").strip().lower()

    if _contains_any(reasoning_lower, _VALUATION_CLAIM_TERMS):
        evidence_terms = _valuation_evidence_terms(asset_key)
        if not _contains_any(reasoning_lower, evidence_terms):
            checklist = "; ".join(asset_evidence_checklist(asset_key))
            issues.append(
                "valuation/relative-value claim is unsupported; cite a relevant metric "
                f"for {asset_class or 'the asset class'} ({checklist}) or remove the claim"
            )

    eth_fee_claim = (
        ("ethereum" in reasoning_lower or " eth" in reasoning_lower or "eth/" in reasoning_lower)
        and ("gas fee" in reasoning_lower or "gas fees" in reasoning_lower or "ethereum fee" in reasoning_lower)
        and _contains_any(reasoning_lower, ("high", "elevated", "expensive", "push", "leaving", "migrat"))
    )
    if eth_fee_claim and not _contains_any(reasoning_lower, ("gwei", "base fee", "fee data", "gas data")):
        issues.append(
            "Ethereum gas-fee migration claim needs current gas-fee evidence (e.g. gwei/base fee) or should be framed as an assumption"
        )

    event_claim = _contains_any(
        reasoning_lower,
        ("summit", "conference", "event", "forum", "meeting"),
    )
    if event_claim and not _contains_any(
        reasoning_lower,
        ("confirmed", "announcement", "launch", "partnership", "release", "decision", "flow", "date"),
    ):
        issues.append(
            "event catalyst is speculative; identify a confirmed announcement/release/flow or label it as narrative support"
        )

    if "will benefit" in reasoning_lower and "assumption" not in reasoning_lower and "if " not in reasoning_lower:
        issues.append(
            "causal claim is stated with too much certainty; separate what is known from what must happen for the trade to work"
        )

    return issues


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
        trade_reasoning = "\n".join(str(t.get("reasoning", "")) for t in active_trades)
        combined_reasoning = "\n".join(p for p in (reasoning, trade_reasoning) if p).strip()
        reasoning_lower = combined_reasoning.lower()

        if not combined_reasoning or len(combined_reasoning) < _MIN_REASONING_LEN:
            issues.append(f"reasoning is too brief ({len(reasoning)} chars — aim for 80+)")
            score -= 0.35

        if not any(kw in reasoning_lower for kw in _SIGNAL_KEYWORDS):
            issues.append("reasoning references no data signals (FRED, prices, Polymarket odds, etc.)")
            score -= 0.30

        generic_count = sum(1 for p in _WEAK_PHRASES if p in reasoning_lower)
        if generic_count >= 2:
            issues.append("reasoning relies on generic macro phrases without a specific catalyst")
            score -= 0.20

        missing_labels = [label for label in _REQUIRED_REASONING_LABELS if label not in reasoning_lower]
        if len(missing_labels) >= 2:
            issues.append(
                "reasoning is not tradeable enough: include THESIS, ENTRY, INVALIDATION, and RISK sections"
            )
            score -= 0.20

        missing_evidence_labels = _missing_evidence_labels(reasoning_lower)
        if len(missing_evidence_labels) >= 3:
            issues.append(
                "reasoning does not clearly separate evidence quality: include FACTS, ASSUMPTIONS, "
                "VALUATION/EVIDENCE, WHY NOW, and TIMEFRAME where relevant"
            )
            score -= 0.15

        claim_issues = _claim_quality_issues(reasoning_lower, asset_class)
        if claim_issues:
            issues.extend(claim_issues)
            score -= min(0.35, 0.18 * len(claim_issues))

        available_catalysts = [
            str(x) for x in (pm_decision.get("available_catalyst_ids") or [])
            if str(x).strip()
        ]
        cited_catalysts = [
            str(x) for x in (pm_decision.get("catalyst_ids") or [])
            if str(x).strip()
        ]
        for trade in active_trades:
            if isinstance(trade, dict):
                cited_catalysts.extend(
                    str(x) for x in (trade.get("catalyst_ids") or [])
                    if str(x).strip()
                )
        explains_non_catalyst = any(
            phrase in reasoning_lower
            for phrase in (
                "not catalyst-driven",
                "not catalyst driven",
                "technical setup",
                "risk-reducing",
                "portfolio rebalance",
            )
        )
        if available_catalysts and not cited_catalysts and not explains_non_catalyst:
            issues.append(
                "non-HOLD trade does not link to a Foresight catalyst or explain why it is not catalyst-driven"
            )
            score -= 0.15

        has_precious_trade = any(str(t.get("symbol", "")).upper() in _PRECIOUS_METALS_SYMBOLS for t in active_trades)
        if has_precious_trade or "gold" in reasoning_lower:
            gold_inputs = {
                "real yields/TIPS": ("real yield" in reasoning_lower or "tips" in reasoning_lower),
                "breakevens/inflation": ("breakeven" in reasoning_lower or "inflation" in reasoning_lower),
                "Fed reaction": ("fed" in reasoning_lower or "fomc" in reasoning_lower),
                "USD/dollar": ("usd" in reasoning_lower or "dollar" in reasoning_lower or "dxy" in reasoning_lower),
            }
            missing_gold_inputs = [name for name, present in gold_inputs.items() if not present]
            if len(missing_gold_inputs) >= 2:
                issues.append(
                    "precious-metals thesis must address real yields/TIPS, inflation breakevens, Fed reaction, and USD"
                )
                score -= 0.20
            if "negative real rates" in reasoning_lower:
                issues.append(
                    "gold thesis claims negative real rates; verify against current TIPS/real-yield data or remove the claim"
                )
                score -= 0.15

        asset_monitor_issues: list[str] = []
        for t in active_trades:
            symbol = str(t.get("symbol", "")).upper()
            _, _, profile = infer_asset_profile(symbol, asset_class, reasoning_lower)
            if not profile:
                continue
            hits, _, _ = profile_coverage(reasoning_lower, profile)
            min_hits = int(profile.get("min_hits", 2))
            if hits < min_hits:
                issue = str(profile.get("issue") or "thesis lacks enough explicit asset-class monitors")
                if issue not in asset_monitor_issues:
                    asset_monitor_issues.append(issue)

        has_asset_monitor_failure = bool(asset_monitor_issues)
        if has_asset_monitor_failure:
            issues.extend(asset_monitor_issues)
            score -= min(0.30, 0.15 * len(asset_monitor_issues))

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
        passed = score >= 0.65 and len(issues) <= 1 and not has_asset_monitor_failure

        feedback = ""
        if issues:
            feedback = (
                "Reasoning quality issues:\n"
                + "\n".join(f"  • {i}" for i in issues)
                + "\n\nRevise by: citing at least one specific data point (e.g. VIX=18, "
                "10Y yield at 4.5%, Polymarket 65% probability), naming a concrete catalyst, "
                "separating verified facts from assumptions, defining why now and timeframe, "
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
            combined_reasoning = "\n".join(
                str(part)
                for part in [
                    pm_decision.get("reasoning") or "",
                    *[t.get("reasoning", "") for t in active_trades],
                ]
                if part
            )
            reasoning_snippet = combined_reasoning[:1200]

            prompt = (
                f"You are auditing a {asset_class} PM's trade reasoning quality.\n"
                f"Proposed trades: {trades_summary}\n"
                f"Reasoning: {reasoning_snippet}\n\n"
                f"Rule-based issues already identified:\n{rule_result.feedback}\n\n"
                f"Check whether the PM separates verified facts from assumptions, supports any "
                f"cheap/undervalued/relative-value claim with asset-class evidence, defines why-now "
                f"and timeframe, and labels speculative catalysts as speculative.\n\n"
                f"Score reasoning quality 0–1:\n"
                f"  0.0 = completely generic, no specific signals cited\n"
                f"  0.5 = some signals mentioned but catalyst unclear\n"
                f"  1.0 = specific, verifiable data + clear catalyst + right instrument\n\n"
                f"Respond with JSON only: "
                f'{{\"quality_score\": 0.6, \"feedback\": \"one specific improvement\"}}'
            )

            resp = llm_chat(
                [{"role": "user", "content": prompt}],
                max_tokens=150,
                task="thesis_verification",
            )
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
