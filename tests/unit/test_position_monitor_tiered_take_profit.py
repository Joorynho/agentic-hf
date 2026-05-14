from datetime import datetime, timezone

from src.backtest.accounting.portfolio import PortfolioAccountant
from src.core.models.enums import Side
from src.core.position_monitor import PositionMonitor


def test_position_monitor_scales_out_at_first_take_profit_level() -> None:
    accountant = PortfolioAccountant("equities", initial_nav=1000.0)
    accountant.record_fill_direct(
        order_id="entry-1",
        symbol="SPY",
        qty=10,
        fill_price=100.0,
        filled_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        take_profit_pct=0.20,
        take_profit_levels=[
            {"trigger_pct": 0.08, "close_pct": 0.25, "label": "TP1"},
            {"trigger_pct": 0.15, "close_pct": 0.50, "label": "TP2"},
        ],
    )
    accountant.mark_to_market({"SPY": 108.5})

    orders = PositionMonitor().check_positions(accountant)

    assert len(orders) == 1
    assert orders[0].symbol == "SPY"
    assert orders[0].side == Side.SELL
    assert orders[0].quantity == 2.5
    assert orders[0].strategy_tag == "position_monitor_tp1"
    assert accountant._entry_metadata["SPY"]["take_profit_hits"] == [0]


def test_position_monitor_keeps_single_take_profit_fallback() -> None:
    accountant = PortfolioAccountant("equities", initial_nav=1000.0)
    accountant.record_fill_direct(
        order_id="entry-1",
        symbol="SPY",
        qty=10,
        fill_price=100.0,
        filled_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        take_profit_pct=0.15,
    )
    accountant.mark_to_market({"SPY": 116.0})

    orders = PositionMonitor().check_positions(accountant)

    assert len(orders) == 1
    assert orders[0].side == Side.SELL
    assert orders[0].quantity == 10
    assert orders[0].strategy_tag == "position_monitor_exit"
