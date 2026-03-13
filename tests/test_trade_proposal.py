"""Tests for enriched TradeProposal and PositionSnapshot models."""
import pytest
from src.core.models.execution import TradeProposal, PositionSnapshot


def test_trade_proposal_has_conviction():
    tp = TradeProposal(action="BUY", symbol="AAPL", qty=10, reasoning="Strong thesis",
                       conviction=0.85)
    assert tp.conviction == 0.85


def test_trade_proposal_conviction_default():
    tp = TradeProposal(action="BUY", symbol="AAPL", qty=10)
    assert tp.conviction == 0.5


def test_trade_proposal_conviction_clamped_high():
    tp = TradeProposal(action="BUY", symbol="AAPL", qty=10, conviction=1.5)
    assert tp.conviction == 1.0


def test_trade_proposal_conviction_clamped_low():
    tp = TradeProposal(action="BUY", symbol="AAPL", qty=10, conviction=-0.3)
    assert tp.conviction == 0.0


def test_trade_proposal_has_strategy_tag():
    tp = TradeProposal(action="BUY", symbol="AAPL", qty=10, strategy_tag="macro_momentum")
    assert tp.strategy_tag == "macro_momentum"


def test_trade_proposal_has_signal_snapshot():
    snap = {"vix": 18.5, "yield_curve": 0.3, "poly_top": "Election 65%"}
    tp = TradeProposal(action="BUY", symbol="AAPL", qty=10, signal_snapshot=snap)
    assert tp.signal_snapshot["vix"] == 18.5


def test_trade_proposal_defaults_backward_compatible():
    tp = TradeProposal(action="SELL", symbol="TSLA", qty=5)
    assert tp.conviction == 0.5
    assert tp.strategy_tag == ""
    assert tp.signal_snapshot == {}
    assert tp.reasoning == ""


def test_position_snapshot_has_entry_thesis():
    ps = PositionSnapshot(symbol="AAPL", qty=10, cost_basis=150.0,
                          current_price=155.0, unrealized_pnl=50.0,
                          entry_thesis="Strong iPhone cycle", entry_date="2026-03-10")
    assert ps.entry_thesis == "Strong iPhone cycle"
    assert ps.entry_date == "2026-03-10"


def test_position_snapshot_defaults_backward_compatible():
    ps = PositionSnapshot(symbol="AAPL", qty=10, cost_basis=150.0,
                          current_price=155.0, unrealized_pnl=50.0)
    assert ps.entry_thesis == ""
    assert ps.entry_date == ""
    assert ps.notional == 1550.0
    assert ps.pnl_pct == pytest.approx(3.333, rel=0.01)
