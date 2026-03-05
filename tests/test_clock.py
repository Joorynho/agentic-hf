import pytest
from datetime import datetime, timedelta
from src.core.clock.simulation_clock import SimulationClock

def test_backtest_clock_advances_by_day():
    clock = SimulationClock(
        start=datetime(2024, 1, 2),
        end=datetime(2024, 1, 5),
        mode="backtest"
    )
    ticks = list(clock)
    assert len(ticks) == 4
    assert ticks[0] == datetime(2024, 1, 2)
    assert ticks[-1] == datetime(2024, 1, 5)

def test_clock_prevents_lookahead():
    clock = SimulationClock(
        start=datetime(2024, 1, 2),
        end=datetime(2024, 1, 10),
        mode="backtest"
    )
    clock.advance()
    current = clock.now()
    assert current == datetime(2024, 1, 3)
    with pytest.raises(ValueError, match="Look-ahead bias"):
        clock.peek_future(datetime(2024, 1, 5))

def test_clock_is_done():
    clock = SimulationClock(
        start=datetime(2024, 1, 2),
        end=datetime(2024, 1, 3),
        mode="backtest"
    )
    assert not clock.is_done()
    clock.advance()
    assert not clock.is_done()
    clock.advance()
    assert clock.is_done()

def test_clock_advance_returns_none_at_end():
    clock = SimulationClock(
        start=datetime(2024, 1, 2),
        end=datetime(2024, 1, 2),
        mode="backtest"
    )
    result = clock.advance()
    assert result is None
