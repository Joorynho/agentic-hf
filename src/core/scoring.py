"""Multi-factor macro regime scoring.

Produces a macro_score in [-1, +1] where:
  +1 = strong risk-on / expansion
  -1 = strong risk-off / contraction
   0 = neutral / mixed signals

Components:
  fred_score (50%): Hard economic data — yield curve, VIX, credit, real rates, inflation
  poly_score (30%): Market-implied expectations from prediction markets
  news_sentiment (20%): Average sentiment polarity from financial news headlines
"""
from __future__ import annotations

import math
import re


def compute_fred_score(snapshot: dict[str, float]) -> float:
    """Multi-factor score from FRED indicators, scaled to [-1, +1].

    1. Yield curve (T10Y2Y): positive = expansion, inverted = recession risk
    2. VIX (VIXCLS): low = calm, high = stress
    3. Credit spread (BAMLH0A0HYM2): tight = risk-on, wide = risk-off
    4. Real rate proxy (DGS10 - T10YIE): negative real rates = stimulative
    5. Inflation expectations (T5YIE): moderate ~2.5% = healthy, extreme = risk
    """
    if not snapshot:
        return 0.0

    components = []

    # 1. Yield curve slope
    slope = snapshot.get("T10Y2Y")
    if slope is not None:
        # +2% → +1.0, 0% → 0.0, -1% → -0.5 (inversion is bad but magnitude matters)
        components.append(max(-1.0, min(1.0, slope / 2.0)))

    # 2. VIX — fear gauge
    vix = snapshot.get("VIXCLS")
    if vix is not None:
        # VIX 12 → +0.8, 18 → +0.2, 22 → -0.2, 30 → -0.8, 40+ → -1.0
        components.append(max(-1.0, min(1.0, (20.0 - vix) / 12.5)))

    # 3. Credit spread
    spread = snapshot.get("BAMLH0A0HYM2")
    if spread is not None:
        # 3% → +0.67, 5% → 0.0, 8% → -1.0
        components.append(max(-1.0, min(1.0, (5.0 - spread) / 3.0)))

    # 4. Real rate proxy: 10Y nominal - 10Y breakeven
    dgs10 = snapshot.get("DGS10")
    t10yie = snapshot.get("T10YIE")
    if dgs10 is not None and t10yie is not None:
        real_rate = dgs10 - t10yie
        # Negative real rate → stimulative (+0.5 to +1.0)
        # Positive real rate > 2% → restrictive (-0.5 to -1.0)
        components.append(max(-1.0, min(1.0, -real_rate / 2.0)))

    # 5. Inflation expectations — moderate is healthy, extreme is risk
    t5yie = snapshot.get("T5YIE")
    if t5yie is not None:
        # 2.0-2.5% → neutral/positive, <1.5% → deflation risk, >3.5% → overheating
        deviation = abs(t5yie - 2.25)
        components.append(max(-1.0, min(1.0, 1.0 - deviation / 1.5)))

    if not components:
        return 0.0
    return sum(components) / len(components)


def compute_poly_score(signals: list) -> float:
    """Score from prediction market signals, scaled to [-1, +1].

    Rather than averaging all probabilities, extract directional macro signals:
    - Rate cut / easing → positive (stimulative)
    - Rate hike / tightening → negative
    - Recession signals → negative
    - Stability / growth → positive

    Falls back to volume-weighted confidence if no macro keywords match.
    """
    if not signals:
        return 0.0

    macro_signals = []
    _BULLISH_PATTERNS = re.compile(
        r"rate\s*cut|lower\s*rate|eas(e|ing)|stimulus|growth|bull|rally|recover|peace|ceasefire",
        re.IGNORECASE,
    )
    _BEARISH_PATTERNS = re.compile(
        r"rate\s*hike|raise\s*rate|tighten|recession|crash|default|war\b|conflict|sanctions|tariff|inflation\s*(rise|spike|surge)",
        re.IGNORECASE,
    )

    for s in signals:
        question = s.get("question", s.get("market", ""))
        prob = s.get("implied_prob", 0.5)
        volume = s.get("volume_24h", 0)
        if not question:
            continue

        if _BULLISH_PATTERNS.search(question):
            # High probability of bullish event → positive score
            macro_signals.append((prob - 0.5) * 2 * max(1, math.log1p(volume / 1000)))
        elif _BEARISH_PATTERNS.search(question):
            # High probability of bearish event → negative score
            macro_signals.append(-(prob - 0.5) * 2 * max(1, math.log1p(volume / 1000)))

    if macro_signals:
        raw = sum(macro_signals) / len(macro_signals)
        return max(-1.0, min(1.0, raw))

    # Fallback: average confidence as a very mild signal
    avg_prob = sum(s.get("implied_prob", 0.5) for s in signals) / len(signals)
    return max(-1.0, min(1.0, (avg_prob - 0.5) * 0.5))


def compute_news_sentiment_score(
    news_sentiments: list[float],
    social_sentiments: list[float],
) -> float:
    """Aggregate news sentiment score, scaled to [-1, +1].

    Averages actual sentiment values from news items. Falls back to an
    activity-based heuristic if all sentiments are zero (backward compat
    with adapters that haven't been updated yet).
    """
    all_vals = list(news_sentiments) + list(social_sentiments)
    if not all_vals:
        return 0.2  # No news is mildly positive

    has_real_sentiment = any(v != 0.0 for v in all_vals)
    if has_real_sentiment:
        return max(-1.0, min(1.0, sum(all_vals) / len(all_vals)))

    # Fallback: activity heuristic (all sentiments are 0.0)
    total = len(all_vals)
    log_items = math.log1p(total)
    baseline = math.log1p(20)
    deviation = (baseline - log_items) / baseline
    return max(-1.0, min(1.0, deviation))


# Keep old name as alias for backward compatibility
compute_activity_score = lambda news_count, social_count: compute_news_sentiment_score(
    [0.0] * news_count, [0.0] * social_count
)


def compute_macro_score(
    fred_snapshot: dict,
    poly_signals: list,
    news_sentiments: list[float] | None = None,
    social_sentiments: list[float] | None = None,
    *,
    news_count: int = 0,
    social_count: int = 0,
) -> dict:
    """Compute the full macro regime score and sub-components.

    Accepts either sentiment value lists (preferred) or item counts
    (backward-compat fallback). Returns dict with: macro_score,
    fred_score, poly_sentiment, social_score, polymarket_confidence.
    """
    fred_score = compute_fred_score(fred_snapshot)
    poly_score = compute_poly_score(poly_signals)

    if news_sentiments is not None or social_sentiments is not None:
        news_score = compute_news_sentiment_score(
            news_sentiments or [], social_sentiments or []
        )
    else:
        news_score = compute_news_sentiment_score(
            [0.0] * news_count, [0.0] * social_count
        )

    # Weighted blend: hard data 50%, market expectations 30%, news sentiment 20%
    available = []
    if fred_snapshot:
        available.append((0.50, fred_score))
    if poly_signals:
        available.append((0.30, poly_score))
    available.append((0.20, news_score))

    if available:
        total_weight = sum(w for w, _ in available)
        macro_score = sum(w * s for w, s in available) / total_weight
    else:
        macro_score = 0.0

    # Confidence: rescale macro_score from [-1,+1] to [0,1]
    confidence = (macro_score + 1.0) / 2.0

    return {
        "macro_score": round(macro_score, 6),
        "fred_score": round(fred_score, 6),
        "poly_sentiment": round(poly_score, 6),
        "social_score": round(news_score, 6),
        "polymarket_confidence": round(confidence, 6),
    }
