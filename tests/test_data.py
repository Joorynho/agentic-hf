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


def test_yfinance_adapter_normalizes_crypto_symbols_for_yahoo():
    cache = ParquetCache(tempfile.mkdtemp())
    adapter = YFinanceAdapter(cache=cache)
    fake_df = MagicMock()
    fake_df.iterrows.return_value = []

    with patch("src.data.adapters.yfinance_adapter.yf.Ticker") as mock_ticker:
        mock_ticker.return_value.history.return_value = fake_df

        bars = adapter._fetch_sync("ETH/USD", date(2024, 1, 2), date(2024, 1, 5))

    mock_ticker.assert_called_once_with("ETH-USD")
    assert bars == []


def test_yfinance_adapter_keeps_original_symbol_on_crypto_bars():
    cache = ParquetCache(tempfile.mkdtemp())
    adapter = YFinanceAdapter(cache=cache)

    with patch("src.data.adapters.yfinance_adapter.yf.Ticker") as mock_ticker:
        mock_ticker.return_value.history.return_value.iterrows.return_value = [
            (
                MagicMock(to_pydatetime=MagicMock(return_value=datetime(2024, 1, 2))),
                {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.5, "Volume": 1234},
            )
        ]

        bars = adapter._fetch_sync("SOL/USD", date(2024, 1, 2), date(2024, 1, 5))

    assert bars[0].symbol == "SOL/USD"
    mock_ticker.assert_called_once_with("SOL-USD")
