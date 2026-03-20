from unittest.mock import MagicMock
from src.data.adapters.multiframe import compute_multiframe, format_multiframe_block

def _make_bars(prices: list[float]) -> list[MagicMock]:
    bars = []
    for p in prices:
        b = MagicMock()
        b.close = p
        bars.append(b)
    return bars

def test_compute_basic():
    prices = list(range(100, 480))   # 380 bars
    bars = _make_bars([float(p) for p in prices])
    result = compute_multiframe(["AAPL"], lambda sym, days: bars)
    assert "AAPL" in result
    d = result["AAPL"]
    assert d["high_52w"] >= d["low_52w"]
    assert d["high_52w"] >= d["current"]
    assert d["low_52w"] <= d["current"]
    assert d["ma_200"] > 0

def test_pct_from_ma_above():
    # All bars at 100 except last bar at 120 -> above MA
    prices = [100.0] * 380
    prices[-1] = 120.0
    bars = _make_bars(prices)
    result = compute_multiframe(["SPY"], lambda s, d: bars)
    assert result["SPY"]["pct_from_ma"] > 0

def test_pct_from_ma_below():
    prices = [100.0] * 380
    prices[-1] = 80.0
    bars = _make_bars(prices)
    result = compute_multiframe(["TLT"], lambda s, d: bars)
    assert result["TLT"]["pct_from_ma"] < 0

def test_insufficient_bars_skipped():
    bars = _make_bars([100.0] * 5)
    result = compute_multiframe(["AAPL"], lambda s, d: bars)
    assert "AAPL" not in result

def test_format_block_contains_symbols():
    mf = {
        "AAPL": {"high_52w": 237.0, "low_52w": 164.0, "ma_200": 220.0, "current": 215.0, "pct_from_ma": -2.3},
        "MSFT": {"high_52w": 450.0, "low_52w": 300.0, "ma_200": 410.0, "current": 420.0, "pct_from_ma": 2.4},
    }
    block = format_multiframe_block(mf)
    assert "AAPL" in block
    assert "MSFT" in block
    assert "52wH" in block
    assert "200dMA" in block
    assert "below" in block or "above" in block

def test_format_empty():
    assert format_multiframe_block({}) == ""
