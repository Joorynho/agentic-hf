"""Tests for market regime classifier.

Credit spread thresholds are calibrated for BAMLH0A0HYM2 (ICE BofA US HY OAS):
  < 3.5% = tight (risk-on), 3.5-5% = normal (neutral),
  5-7% = widening (risk-off), > 7% = blowout (crisis)
"""
import pytest
from src.core.regime import classify_regime


def test_risk_on_regime():
    # HY spread 2.8% = tight → risk-on signal
    r = classify_regime(vix=12, yield_curve=0.8, credit_spread=2.8)
    assert r.regime == "risk_on"
    assert r.scale == 1.2
    assert r.score >= 2


def test_neutral_regime():
    # HY spread 4.0% = normal range → neutral signal
    r = classify_regime(vix=20, yield_curve=0.3, credit_spread=4.0)
    assert r.regime == "neutral"
    assert r.scale == 1.0


def test_risk_off_regime():
    # VIX 28 = elevated (-1), yield_curve 0.3 = neutral (0), HY 5.5% = widening (-1) → score -2 = risk_off
    r = classify_regime(vix=28, yield_curve=0.3, credit_spread=5.5)
    assert r.regime == "risk_off"
    assert r.scale == 0.7


def test_crisis_regime():
    # VIX 40 (-2), deeply inverted (-2), HY 8% blowout (-2) → score -6 = crisis
    r = classify_regime(vix=40, yield_curve=-0.8, credit_spread=8.0)
    assert r.regime == "crisis"
    assert r.scale == 0.4
    assert r.score <= -3


def test_no_data_defaults_neutral():
    r = classify_regime()
    assert r.regime == "neutral"
    assert r.scale == 1.0


def test_partial_data_vix_only():
    r = classify_regime(vix=10)
    assert r.regime in ("risk_on", "neutral")
    assert r.vix == 10
    assert r.yield_curve is None


def test_partial_data_mixed():
    r = classify_regime(vix=30, yield_curve=1.0)
    assert r.regime in ("neutral", "risk_off")


def test_classification_has_description():
    r = classify_regime(vix=12, yield_curve=0.8)
    assert r.label == "Risk-On"
    assert "growth" in r.description.lower() or "risk" in r.description.lower()


def test_boundary_vix_25():
    # HY 4.0% = normal/neutral (no signal either way)
    r = classify_regime(vix=25, yield_curve=0.3, credit_spread=4.0)
    assert r.regime in ("neutral", "risk_off")


def test_extreme_crisis():
    # HY 9% = deep blowout → crisis
    r = classify_regime(vix=50, yield_curve=-1.0, credit_spread=9.0)
    assert r.regime == "crisis"
    assert r.scale == 0.4


def test_hy_spread_thresholds():
    """Verify each HY spread bucket maps correctly."""
    # Tight (<3.5%) → +1
    r = classify_regime(credit_spread=3.0)
    assert r.score == 1

    # Normal (3.5-5%) → 0
    r = classify_regime(credit_spread=4.5)
    assert r.score == 0

    # Widening (5-7%) → -1
    r = classify_regime(credit_spread=6.0)
    assert r.score == -1

    # Blowout (>7%) → -2
    r = classify_regime(credit_spread=8.0)
    assert r.score == -2
