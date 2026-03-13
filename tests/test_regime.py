"""Tests for market regime classifier."""
import pytest
from src.core.regime import classify_regime


def test_risk_on_regime():
    r = classify_regime(vix=12, yield_curve=0.8, credit_spread=0.7)
    assert r.regime == "risk_on"
    assert r.scale == 1.2
    assert r.score >= 2


def test_neutral_regime():
    r = classify_regime(vix=20, yield_curve=0.3, credit_spread=1.5)
    assert r.regime == "neutral"
    assert r.scale == 1.0


def test_risk_off_regime():
    r = classify_regime(vix=28, yield_curve=0.3, credit_spread=2.5)
    assert r.regime == "risk_off"
    assert r.scale == 0.7


def test_crisis_regime():
    r = classify_regime(vix=40, yield_curve=-0.8, credit_spread=4.0)
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
    r = classify_regime(vix=25, yield_curve=0.3, credit_spread=1.5)
    assert r.regime in ("neutral", "risk_off")


def test_extreme_crisis():
    r = classify_regime(vix=50, yield_curve=-1.0, credit_spread=5.0)
    assert r.regime == "crisis"
    assert r.scale == 0.4
