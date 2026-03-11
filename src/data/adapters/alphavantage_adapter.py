"""Alpha Vantage adapter — backup source for stocks and crypto quotes.

Free tier: 25 requests/day. Standard: 5 req/min.
Docs: https://www.alphavantage.co/documentation/
"""
from __future__ import annotations

import asyncio
import logging
import os
import time

logger = logging.getLogger(__name__)

API_BASE = "https://www.alphavantage.co/query"
CACHE_TTL = 60.0
REQUEST_TIMEOUT = 10


class AlphaVantageAdapter:
    """Backup quote source via Alpha Vantage (stocks + crypto)."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.getenv("ALPHA_VANTAGE_API_KEY", "")
        self._cache: dict[str, tuple[float, dict]] = {}

    def is_configured(self) -> bool:
        return bool(self._api_key)

    async def fetch_quote(self, symbol: str) -> dict | None:
        """Fetch a stock/ETF quote using GLOBAL_QUOTE."""
        now = time.time()
        cached = self._cache.get(symbol)
        if cached and (now - cached[0]) < CACHE_TTL:
            return cached[1]

        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(self._fetch_stock_sync, symbol),
                timeout=REQUEST_TIMEOUT,
            )
            if result:
                self._cache[symbol] = (now, result)
            return result
        except asyncio.TimeoutError:
            logger.debug("[alphavantage] Timeout fetching %s", symbol)
            return cached[1] if cached else None
        except Exception as exc:
            logger.debug("[alphavantage] Failed to fetch %s: %s", symbol, exc)
            return cached[1] if cached else None

    async def fetch_crypto_quote(self, symbol: str) -> dict | None:
        """Fetch a crypto quote using CURRENCY_EXCHANGE_RATE."""
        clean = self._normalize_crypto(symbol)
        cache_key = f"crypto:{clean}"
        now = time.time()
        cached = self._cache.get(cache_key)
        if cached and (now - cached[0]) < CACHE_TTL:
            return cached[1]

        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(self._fetch_crypto_sync, clean, symbol),
                timeout=REQUEST_TIMEOUT,
            )
            if result:
                self._cache[cache_key] = (now, result)
            return result
        except asyncio.TimeoutError:
            logger.debug("[alphavantage] Timeout fetching crypto %s", symbol)
            return cached[1] if cached else None
        except Exception as exc:
            logger.debug("[alphavantage] Failed to fetch crypto %s: %s", symbol, exc)
            return cached[1] if cached else None

    async def fetch_quotes(self, symbols: list[str]) -> dict[str, dict]:
        """Fetch multiple quotes (sequential to respect rate limits)."""
        results: dict[str, dict] = {}
        for symbol in symbols:
            if self._is_crypto(symbol):
                quote = await self.fetch_crypto_quote(symbol)
            else:
                quote = await self.fetch_quote(symbol)
            if quote:
                results[symbol] = quote
        return results

    def _fetch_stock_sync(self, symbol: str) -> dict | None:
        import requests

        params = {
            "function": "GLOBAL_QUOTE",
            "symbol": symbol,
            "apikey": self._api_key,
        }

        resp = requests.get(API_BASE, params=params, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            return None

        data = resp.json()
        gq = data.get("Global Quote", {})
        if not gq or not gq.get("05. price"):
            if "Note" in data or "Information" in data:
                logger.debug("[alphavantage] Rate-limited: %s", data.get("Note") or data.get("Information"))
            return None

        return {
            "symbol": gq.get("01. symbol", symbol),
            "name": "",
            "price": float(gq.get("05. price", 0)),
            "change_amount": float(gq.get("09. change", 0)),
            "change_pct": float(gq.get("10. change percent", "0%").rstrip("%")),
            "source": "alphavantage",
        }

    def _fetch_crypto_sync(self, clean_symbol: str, original: str) -> dict | None:
        import requests

        params = {
            "function": "CURRENCY_EXCHANGE_RATE",
            "from_currency": clean_symbol,
            "to_currency": "USD",
            "apikey": self._api_key,
        }

        resp = requests.get(API_BASE, params=params, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            return None

        data = resp.json()
        rate_data = data.get("Realtime Currency Exchange Rate", {})
        if not rate_data or not rate_data.get("5. Exchange Rate"):
            if "Note" in data or "Information" in data:
                logger.debug("[alphavantage] Rate-limited (crypto): %s",
                             data.get("Note") or data.get("Information"))
            return None

        return {
            "symbol": original,
            "name": rate_data.get("2. From_Currency Name", ""),
            "price": float(rate_data.get("5. Exchange Rate", 0)),
            "change_amount": 0.0,
            "change_pct": 0.0,
            "source": "alphavantage",
        }

    @staticmethod
    def _normalize_crypto(symbol: str) -> str:
        s = symbol.strip().upper()
        if "/" in s:
            s = s.split("/")[0]
        return s

    @staticmethod
    def _is_crypto(symbol: str) -> bool:
        return "/" in symbol
