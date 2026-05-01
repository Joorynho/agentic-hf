"""Slippage fields on record_fill_direct."""

from datetime import datetime, timezone

import pytest

from src.backtest.accounting.portfolio import PortfolioAccountant


def test_record_fill_direct_slippage_bps():
    acct = PortfolioAccountant(pod_id="equities", initial_nav=100_000.0)
    acct.record_fill_direct(
        order_id="o1",
        symbol="SPY",
        qty=10.0,
        fill_price=100.5,
        filled_at=datetime.now(timezone.utc),
        expected_price=100.0,
    )
    fl = acct._fill_log[-1]
    assert fl.get("expected_price") == 100.0
    assert fl.get("slippage_bps") is not None
    assert abs(fl["slippage_bps"] - 50.0) < 0.1


def test_no_expected_price_no_slippage():
    acct = PortfolioAccountant(pod_id="equities", initial_nav=100_000.0)
    acct.record_fill_direct(
        order_id="o2",
        symbol="SPY",
        qty=5.0,
        fill_price=200.0,
        filled_at=datetime.now(timezone.utc),
    )
    fl = acct._fill_log[-1]
    assert fl.get("expected_price") is None
    assert fl.get("slippage_bps") is None
