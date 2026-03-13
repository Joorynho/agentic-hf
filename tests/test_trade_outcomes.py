"""Tests for closed trade tracking with entry metadata in PortfolioAccountant."""
import pytest
from datetime import datetime, timezone

from src.backtest.accounting.portfolio import PortfolioAccountant


def _make_accountant(pod_id="test_pod", nav=100_000.0):
    return PortfolioAccountant(pod_id=pod_id, initial_nav=nav)


def test_closed_trade_records_metadata():
    acc = _make_accountant()
    t1 = datetime(2026, 3, 10, 10, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 3, 12, 14, 30, tzinfo=timezone.utc)

    acc.record_fill_direct("o1", "AAPL", qty=10, fill_price=150.0, filled_at=t1,
                           reasoning="Strong iPhone cycle", conviction=0.8,
                           strategy_tag="macro_momentum",
                           signal_snapshot={"vix": 18.5})

    acc.record_fill_direct("o2", "AAPL", qty=-10, fill_price=160.0, filled_at=t2)

    trades = acc.closed_trades
    assert len(trades) == 1
    ct = trades[0]
    assert ct["symbol"] == "AAPL"
    assert ct["entry_price"] == 150.0
    assert ct["exit_price"] == 160.0
    assert ct["realized_pnl"] == pytest.approx(100.0)
    assert ct["entry_reasoning"] == "Strong iPhone cycle"
    assert ct["conviction"] == 0.8
    assert ct["strategy_tag"] == "macro_momentum"
    assert ct["signal_snapshot"]["vix"] == 18.5
    assert ct["side"] == "long"


def test_partial_close_records_trade():
    acc = _make_accountant()
    t1 = datetime(2026, 3, 10, tzinfo=timezone.utc)
    t2 = datetime(2026, 3, 11, tzinfo=timezone.utc)
    t3 = datetime(2026, 3, 12, tzinfo=timezone.utc)

    acc.record_fill_direct("o1", "MSFT", qty=20, fill_price=400.0, filled_at=t1,
                           reasoning="Cloud growth", conviction=0.7)

    # Partial close: sell 10
    acc.record_fill_direct("o2", "MSFT", qty=-10, fill_price=420.0, filled_at=t2)
    trades = acc.closed_trades
    assert len(trades) == 1
    assert trades[0]["qty"] == 10
    assert trades[0]["realized_pnl"] == pytest.approx(200.0)

    # Full close: sell remaining 10
    acc.record_fill_direct("o3", "MSFT", qty=-10, fill_price=410.0, filled_at=t3)
    trades = acc.closed_trades
    assert len(trades) == 2
    assert trades[1]["realized_pnl"] == pytest.approx(100.0)


def test_no_closed_trades_on_open():
    acc = _make_accountant()
    acc.record_fill_direct("o1", "TSLA", qty=5, fill_price=200.0,
                           reasoning="EV thesis", conviction=0.6)
    assert acc.closed_trades == []


def test_entry_metadata_cleared_after_full_close():
    acc = _make_accountant()
    t1 = datetime(2026, 3, 10, tzinfo=timezone.utc)
    acc.record_fill_direct("o1", "GOOG", qty=5, fill_price=100.0, filled_at=t1,
                           reasoning="Ad revenue")
    acc.record_fill_direct("o2", "GOOG", qty=-5, fill_price=110.0)

    # Metadata should be cleaned up after full close
    assert "GOOG" not in acc._entry_metadata
    assert "GOOG" not in acc._entry_theses


def test_short_position_closed_trade():
    acc = _make_accountant()
    t1 = datetime(2026, 3, 10, tzinfo=timezone.utc)
    acc.record_fill_direct("o1", "SPY", qty=-10, fill_price=500.0, filled_at=t1,
                           reasoning="Bear signal", conviction=0.9)
    acc.record_fill_direct("o2", "SPY", qty=10, fill_price=490.0)

    trades = acc.closed_trades
    assert len(trades) == 1
    assert trades[0]["side"] == "short"
    assert trades[0]["realized_pnl"] == pytest.approx(100.0)


def test_entry_thesis_in_position_snapshot():
    acc = _make_accountant()
    t1 = datetime(2026, 3, 10, tzinfo=timezone.utc)
    acc.record_fill_direct("o1", "NVDA", qty=5, fill_price=800.0, filled_at=t1,
                           reasoning="AI infrastructure boom")

    positions = acc.current_positions
    assert "NVDA" in positions
    assert positions["NVDA"].entry_thesis == "AI infrastructure boom"
    assert positions["NVDA"].entry_date == "2026-03-10"
