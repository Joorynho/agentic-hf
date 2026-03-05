import pytest
import tempfile
from datetime import date

from src.data.adapters.yfinance_adapter import YFinanceAdapter
from src.data.cache.parquet_cache import ParquetCache


@pytest.mark.asyncio
async def test_fetch_bars_returns_bar_objects():
    cache_dir = tempfile.mkdtemp()
    adapter = YFinanceAdapter(cache=ParquetCache(cache_dir))
    bars = await adapter.fetch(symbol="AAPL", start=date(2024, 1, 2), end=date(2024, 1, 10))
    assert len(bars) > 0
    assert bars[0].symbol == "AAPL"
    assert bars[0].close > 0


@pytest.mark.asyncio
async def test_cache_avoids_refetch():
    cache_dir = tempfile.mkdtemp()
    cache = ParquetCache(cache_dir)
    adapter = YFinanceAdapter(cache=cache)
    bars1 = await adapter.fetch("SPY", date(2024, 1, 2), date(2024, 1, 5))
    bars2 = await adapter.fetch("SPY", date(2024, 1, 2), date(2024, 1, 5))
    assert len(bars1) == len(bars2)


def test_completeness_score():
    cache = ParquetCache(tempfile.mkdtemp())
    score = cache.completeness_score("NONEXIST", date(2024, 1, 2), date(2024, 1, 5))
    assert score == 0.0
