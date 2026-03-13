import pytest
import tempfile
from datetime import date, datetime
from unittest.mock import patch, MagicMock

from src.core.models.market import Bar
from src.data.adapters.yfinance_adapter import YFinanceAdapter
from src.data.cache.parquet_cache import ParquetCache


def _fake_bars(symbol, start, end):
    """Generate synthetic bars without hitting Yahoo Finance."""
    return [
        Bar(symbol=symbol, timestamp=datetime(2024, 1, d),
            open=180.0 + d, high=182.0 + d, low=178.0 + d, close=181.0 + d,
            volume=1_000_000, source="test")
        for d in range(2, 6)
    ]


@pytest.mark.asyncio
async def test_fetch_bars_returns_bar_objects():
    cache_dir = tempfile.mkdtemp()
    adapter = YFinanceAdapter(cache=ParquetCache(cache_dir))
    with patch.object(adapter, "_fetch_sync", side_effect=lambda s, st, en: _fake_bars(s, st, en)):
        bars = await adapter.fetch(symbol="AAPL", start=date(2024, 1, 2), end=date(2024, 1, 10))
    assert len(bars) > 0
    assert bars[0].symbol == "AAPL"
    assert bars[0].close > 0


@pytest.mark.asyncio
async def test_cache_avoids_refetch():
    cache_dir = tempfile.mkdtemp()
    cache = ParquetCache(cache_dir)
    adapter = YFinanceAdapter(cache=cache)
    with patch.object(adapter, "_fetch_sync", side_effect=lambda s, st, en: _fake_bars(s, st, en)) as mock_fetch:
        bars1 = await adapter.fetch("SPY", date(2024, 1, 2), date(2024, 1, 5))
        bars2 = await adapter.fetch("SPY", date(2024, 1, 2), date(2024, 1, 5))
    assert len(bars1) == len(bars2)
    assert mock_fetch.call_count == 1  # second call served from cache


def test_completeness_score():
    cache = ParquetCache(tempfile.mkdtemp())
    score = cache.completeness_score("NONEXIST", date(2024, 1, 2), date(2024, 1, 5))
    assert score == 0.0
