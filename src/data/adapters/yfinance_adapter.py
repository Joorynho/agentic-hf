from __future__ import annotations

import asyncio
import logging
from datetime import date

import yfinance as yf

from .base import DataAdapter
from ..cache.parquet_cache import ParquetCache
from src.core.models.market import Bar
from src.data.adapters.price_service import is_crypto_symbol, yfinance_crypto_symbol

logger = logging.getLogger(__name__)


class YFinanceAdapter(DataAdapter):
    def __init__(self, cache: ParquetCache):
        self._cache = cache

    async def fetch(self, symbol: str, start: date, end: date) -> list[Bar]:
        cached = self._cache.get(symbol, start, end)
        if cached:
            return cached
        bars = await asyncio.get_event_loop().run_in_executor(
            None, self._fetch_sync, symbol, start, end
        )
        self._cache.save(symbol, bars)
        return bars

    def _fetch_sync(self, symbol: str, start: date, end: date) -> list[Bar]:
        yahoo_symbol = yfinance_crypto_symbol(symbol) if is_crypto_symbol(symbol) else symbol
        try:
            ticker = yf.Ticker(yahoo_symbol)
            df = ticker.history(start=str(start), end=str(end), auto_adjust=True)
        except Exception as exc:
            logger.debug("[yfinance_adapter] history fetch failed for %s via %s: %s", symbol, yahoo_symbol, exc)
            return []
        bars = []
        for ts, row in df.iterrows():
            bars.append(Bar(
                symbol=symbol,
                timestamp=ts.to_pydatetime().replace(tzinfo=None),
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=float(row["Volume"]),
                adj_close=float(row["Close"]),
                source="yfinance",
            ))
        return bars
