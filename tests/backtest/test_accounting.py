import pytest
from datetime import datetime
from uuid import uuid4

from src.backtest.accounting.portfolio import PortfolioAccountant
from src.core.models.execution import Fill
from src.core.models.enums import Side


def make_fill(symbol, side, qty, price):
    return Fill(
        order_id=uuid4(),
        pod_id="alpha",
        symbol=symbol,
        side=side,
        quantity=qty,
        price=price,
        commission=qty * price * 0.0005,
        timestamp=datetime.now(),
    )


def test_buy_creates_position():
    acc = PortfolioAccountant(pod_id="alpha", initial_nav=1_000_000)
    fill = make_fill("AAPL", Side.BUY, 100, 185.0)
    acc.record_fill(fill)
    pos = acc.get_position("AAPL")
    assert pos.quantity == 100
    assert abs(pos.avg_cost - 185.0) < 0.01


def test_pnl_calculated_correctly():
    acc = PortfolioAccountant(pod_id="alpha", initial_nav=1_000_000)
    fill = make_fill("AAPL", Side.BUY, 100, 185.0)
    acc.record_fill(fill)
    acc.mark_to_market({"AAPL": 190.0})
    pos = acc.get_position("AAPL")
    assert abs(pos.unrealised_pnl - 500.0) < 1.0


def test_drawdown_tracked_from_hwm():
    acc = PortfolioAccountant(pod_id="alpha", initial_nav=1_000_000)
    acc.mark_to_market({})  # NAV = 1M, HWM = 1M
    fill = make_fill("AAPL", Side.BUY, 100, 185.0)
    acc.record_fill(fill)
    acc.mark_to_market({"AAPL": 180.0})
    assert acc.drawdown_from_hwm() < 0


def test_sell_closes_position():
    acc = PortfolioAccountant(pod_id="alpha", initial_nav=1_000_000)
    acc.record_fill(make_fill("AAPL", Side.BUY, 100, 185.0))
    acc.record_fill(make_fill("AAPL", Side.SELL, 100, 190.0))
    assert acc.get_position("AAPL") is None
