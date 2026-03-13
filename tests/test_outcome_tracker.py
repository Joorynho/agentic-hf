"""Tests for TradeOutcomeTracker."""
import pytest
from src.core.trade_outcomes import TradeOutcomeTracker


def _make_trades():
    return [
        {"symbol": "AAPL", "realized_pnl": 100.0, "entry_price": 150.0,
         "exit_price": 160.0, "conviction": 0.8, "strategy_tag": "momentum"},
        {"symbol": "TSLA", "realized_pnl": -50.0, "entry_price": 200.0,
         "exit_price": 195.0, "conviction": 0.6, "strategy_tag": "mean_reversion"},
        {"symbol": "AAPL", "realized_pnl": 75.0, "entry_price": 155.0,
         "exit_price": 162.5, "conviction": 0.7, "strategy_tag": "momentum"},
        {"symbol": "GOOG", "realized_pnl": -25.0, "entry_price": 100.0,
         "exit_price": 97.5, "conviction": 0.5, "strategy_tag": "value"},
    ]


def test_empty_tracker():
    t = TradeOutcomeTracker("equities")
    assert t.total_trades == 0
    assert t.win_rate == 0.0
    assert t.avg_pnl == 0.0
    assert t.format_for_prompt() == "No closed trades yet."


def test_ingest_and_stats():
    t = TradeOutcomeTracker("equities")
    trades = _make_trades()
    t.ingest(trades)

    assert t.total_trades == 4
    assert t.win_rate == pytest.approx(0.5)
    assert t.avg_pnl == pytest.approx(25.0)
    assert t.total_pnl == pytest.approx(100.0)
    assert t.avg_winner == pytest.approx(87.5)
    assert t.avg_loser == pytest.approx(-37.5)


def test_per_symbol_stats():
    t = TradeOutcomeTracker("equities")
    t.ingest(_make_trades())
    stats = t.per_symbol_stats()

    assert "AAPL" in stats
    assert stats["AAPL"]["trades"] == 2
    assert stats["AAPL"]["wins"] == 2
    assert stats["AAPL"]["win_rate"] == pytest.approx(1.0)
    assert stats["AAPL"]["total_pnl"] == pytest.approx(175.0)


def test_format_for_prompt():
    t = TradeOutcomeTracker("equities")
    t.ingest(_make_trades())
    prompt = t.format_for_prompt()

    assert "4 trades" in prompt
    assert "50% win rate" in prompt
    assert "AAPL" in prompt
    assert "Last" in prompt


def test_ingest_deduplicates():
    t = TradeOutcomeTracker("equities")
    trades = _make_trades()
    t.ingest(trades[:2])
    assert t.total_trades == 2
    t.ingest(trades[:2])
    assert t.total_trades == 2
    t.ingest(trades)
    assert t.total_trades == 4


def test_serialization_roundtrip():
    t = TradeOutcomeTracker("equities")
    t.ingest(_make_trades())

    state = t.to_state_dict()
    assert state["pod_id"] == "equities"
    assert len(state["trades"]) == 4

    restored = TradeOutcomeTracker.load_from_state(state)
    assert restored.total_trades == 4
    assert restored.win_rate == pytest.approx(0.5)
    assert restored.total_pnl == pytest.approx(100.0)
