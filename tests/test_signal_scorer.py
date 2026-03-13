"""Tests for SignalScorer."""
import pytest
from src.core.signal_scorer import SignalScorer


def test_empty_scorer():
    s = SignalScorer("equities")
    assert s.get_hit_rates() == {}
    assert s.format_for_prompt() == ""


def test_record_and_hit_rates():
    s = SignalScorer("equities")
    s.record_trade({"vix": 12, "yield_curve": 0.8}, realized_pnl=100.0)
    s.record_trade({"vix": 14, "yield_curve": 0.6}, realized_pnl=50.0)
    s.record_trade({"vix": 11, "yield_curve": 0.9}, realized_pnl=-30.0)

    rates = s.get_hit_rates()
    assert "vix_level" in rates
    vix_low = rates["vix_level"]["low (<15)"]
    assert vix_low["trades"] == 3
    assert vix_low["wins"] == 2
    assert vix_low["hit_rate"] == pytest.approx(2 / 3)


def test_vix_buckets():
    s = SignalScorer("equities")
    s.record_trade({"vix": 10}, realized_pnl=100.0)
    s.record_trade({"vix": 20}, realized_pnl=-50.0)
    s.record_trade({"vix": 30}, realized_pnl=-100.0)

    rates = s.get_hit_rates()
    assert "low (<15)" in rates["vix_level"]
    assert "mid (15-25)" in rates["vix_level"]
    assert "high (>25)" in rates["vix_level"]


def test_yield_curve_buckets():
    s = SignalScorer("equities")
    s.record_trade({"yield_curve": -0.5}, realized_pnl=100.0)
    s.record_trade({"yield_curve": 0.2}, realized_pnl=-50.0)
    s.record_trade({"yield_curve": 1.5}, realized_pnl=200.0)

    rates = s.get_hit_rates()
    assert "inverted" in rates["yield_curve"]
    assert "flat" in rates["yield_curve"]
    assert "normal" in rates["yield_curve"]


def test_macro_outlook_tracking():
    s = SignalScorer("equities")
    s.record_trade({"macro_outlook": "bullish"}, realized_pnl=100.0)
    s.record_trade({"macro_outlook": "bullish"}, realized_pnl=-20.0)
    s.record_trade({"macro_outlook": "bearish"}, realized_pnl=-80.0)

    rates = s.get_hit_rates()
    assert rates["macro_outlook"]["bullish"]["hit_rate"] == pytest.approx(0.5)
    assert rates["macro_outlook"]["bearish"]["hit_rate"] == pytest.approx(0.0)


def test_format_for_prompt_min_trades():
    s = SignalScorer("equities")
    # Only 1 trade — should not appear (min 2 required)
    s.record_trade({"vix": 10}, realized_pnl=100.0)
    assert s.format_for_prompt() == ""

    s.record_trade({"vix": 12}, realized_pnl=-50.0)
    prompt = s.format_for_prompt()
    assert "vix_level" in prompt
    assert "hit rate" in prompt


def test_ingest_closed_trades():
    s = SignalScorer("equities")
    trades = [
        {"signal_snapshot": {"vix": 15, "yield_curve": 0.3}, "realized_pnl": 100.0},
        {"signal_snapshot": {"vix": 22}, "realized_pnl": -50.0},
        {"signal_snapshot": {}, "realized_pnl": 25.0},
    ]
    s.ingest_closed_trades(trades)
    rates = s.get_hit_rates()
    assert rates["vix_level"]["mid (15-25)"]["trades"] == 2


def test_serialization_roundtrip():
    s = SignalScorer("equities")
    s.record_trade({"vix": 12, "macro_outlook": "bullish"}, realized_pnl=100.0)
    s.record_trade({"vix": 14, "macro_outlook": "bullish"}, realized_pnl=-50.0)

    state = s.to_state_dict()
    restored = SignalScorer.load_from_state(state)

    assert restored.get_hit_rates() == s.get_hit_rates()
    assert restored._pod_id == "equities"
