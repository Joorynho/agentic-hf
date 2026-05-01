"""CRO firm drawdown tiers."""

import pytest

from src.agents.risk.cro_agent import CROAgent
from src.core.bus.event_bus import EventBus


@pytest.fixture
def cro():
    return CROAgent(bus=EventBus())


def test_drawdown_none_when_no_peak(cro):
    r = cro.check_firm_drawdown(0, 100_000)
    assert r["tier"] == "none"


def test_drawdown_halt_at_minus_10pct(cro):
    peak = 100_000.0
    cur = 89_000.0
    r = cro.check_firm_drawdown(peak, cur)
    assert r["tier"] == "halt"
    assert r["drawdown_pct"] < -0.09


def test_drawdown_orange_at_minus_8pct(cro):
    peak = 100_000.0
    cur = 91_000.0
    r = cro.check_firm_drawdown(peak, cur)
    assert r["tier"] == "orange"


def test_drawdown_yellow_at_minus_5pct(cro):
    peak = 100_000.0
    cur = 94_000.0
    r = cro.check_firm_drawdown(peak, cur)
    assert r["tier"] == "yellow"


def test_drawdown_none_at_minus_4pct(cro):
    peak = 100_000.0
    cur = 96_000.0
    r = cro.check_firm_drawdown(peak, cur)
    assert r["tier"] == "none"
