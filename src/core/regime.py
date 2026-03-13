"""Market regime classifier using VIX, yield curve, and credit spreads.

Outputs a regime label and position sizing multiplier:
  risk_on  → 1.2x (low vol, steep curve, tight spreads)
  neutral  → 1.0x (mixed signals)
  risk_off → 0.7x (elevated vol, flat/inverted curve, widening spreads)
  crisis   → 0.4x (extreme vol, inverted curve, wide spreads)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

REGIMES = {
    "risk_on":  {"label": "Risk-On",  "scale": 1.2, "desc": "Low volatility, steep yield curve — favor growth/risk assets"},
    "neutral":  {"label": "Neutral",  "scale": 1.0, "desc": "Mixed signals — standard position sizing"},
    "risk_off": {"label": "Risk-Off", "scale": 0.7, "desc": "Elevated volatility or flat curve — reduce exposure"},
    "crisis":   {"label": "Crisis",   "scale": 0.4, "desc": "Extreme stress — minimal positions, preserve capital"},
}


@dataclass
class RegimeClassification:
    regime: str  # risk_on | neutral | risk_off | crisis
    scale: float
    label: str
    description: str
    vix: float | None
    yield_curve: float | None
    credit_spread: float | None
    score: int  # -3 to +3 raw score before bucketing


def classify_regime(
    vix: float | None = None,
    yield_curve: float | None = None,
    credit_spread: float | None = None,
) -> RegimeClassification:
    """Classify the current market regime based on available indicators.

    Args:
        vix: CBOE VIX index value (e.g. 15.5)
        yield_curve: 10Y-2Y Treasury spread in percentage points (e.g. 0.5 = 50bps)
        credit_spread: Investment-grade credit spread in percentage points (e.g. 1.2)

    Returns:
        RegimeClassification with regime name, sizing scale, and description
    """
    score = 0
    contributions = 0

    if vix is not None:
        contributions += 1
        if vix < 15:
            score += 1   # Low vol → risk-on signal
        elif vix < 25:
            pass         # Normal → neutral
        elif vix < 35:
            score -= 1   # Elevated → risk-off signal
        else:
            score -= 2   # Extreme → crisis signal

    if yield_curve is not None:
        contributions += 1
        if yield_curve > 0.5:
            score += 1   # Steep → risk-on
        elif yield_curve > -0.1:
            pass         # Flat → neutral
        elif yield_curve > -0.5:
            score -= 1   # Mildly inverted → risk-off
        else:
            score -= 2   # Deeply inverted → crisis

    if credit_spread is not None:
        contributions += 1
        if credit_spread < 1.0:
            score += 1   # Tight spreads → risk-on
        elif credit_spread < 2.0:
            pass         # Normal → neutral
        elif credit_spread < 3.5:
            score -= 1   # Widening → risk-off
        else:
            score -= 2   # Blowout → crisis

    if contributions == 0:
        regime_key = "neutral"
    elif score >= 2:
        regime_key = "risk_on"
    elif score >= 0:
        regime_key = "neutral"
    elif score >= -2:
        regime_key = "risk_off"
    else:
        regime_key = "crisis"

    r = REGIMES[regime_key]
    return RegimeClassification(
        regime=regime_key,
        scale=r["scale"],
        label=r["label"],
        description=r["desc"],
        vix=vix,
        yield_curve=yield_curve,
        credit_spread=credit_spread,
        score=score,
    )
