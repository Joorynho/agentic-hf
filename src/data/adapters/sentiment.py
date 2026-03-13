"""Shared keyword-based sentiment scoring for financial news.

Used by RSS, GDELT, and X (news feed) adapters to compute headline
sentiment on a [-1, +1] scale. Bullish keywords push positive, bearish
keywords push negative, magnitude scales with the ratio of matches.
"""
from __future__ import annotations

BULLISH_WORDS: list[str] = [
    "rally", "surge", "breakout", "bullish", "upside", "beat", "strong",
    "growth", "soar", "boom", "gain", "record high", "all-time high",
    "recovery", "optimism", "dovish", "easing", "stimulus", "upgrade",
    "outperform", "accelerat", "expand", "positive", "green",
]

BEARISH_WORDS: list[str] = [
    "crash", "plunge", "bearish", "downside", "miss", "weak", "recession",
    "crisis", "collapse", "sell-off", "selloff", "tumble", "slump", "drop",
    "decline", "fear", "hawkish", "tightening", "downgrade", "default",
    "underperform", "contract", "negative", "red", "warning", "risk",
    "inflation surge", "rate hike", "layoff", "bankruptcy",
]


def compute_keyword_sentiment(text: str) -> float:
    """Keyword-based sentiment scoring, clamped to [-1, +1].

    Counts bullish vs bearish keyword hits in lowercased text.
    Returns (bullish - bearish) / total_hits, or 0.0 if no hits.
    """
    lower = text.lower()
    bullish = sum(1 for w in BULLISH_WORDS if w in lower)
    bearish = sum(1 for w in BEARISH_WORDS if w in lower)
    total = bullish + bearish
    if total == 0:
        return 0.0
    return max(-1.0, min(1.0, (bullish - bearish) / total))


def sentiment_label(score: float) -> str:
    """Map a sentiment score to a human-readable label."""
    if score > 0.1:
        return "bullish"
    elif score < -0.1:
        return "bearish"
    return "neutral"
