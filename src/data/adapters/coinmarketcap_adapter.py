"""CoinMarketCap adapter — real-time crypto quotes via CMC API.

Free tier: 10,000 credits/month, 30 req/min, no historical data.
Docs: https://coinmarketcap.com/api/documentation/v1/
"""
from __future__ import annotations

import asyncio
import logging
import os
import time

logger = logging.getLogger(__name__)

API_BASE = "https://pro-api.coinmarketcap.com"
CACHE_TTL = 30.0
REQUEST_TIMEOUT = 10


class CoinMarketCapAdapter:
    """Fetches real-time crypto quotes from CoinMarketCap."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.getenv("COINMARKETCAP_API_KEY", "")
        self._cache: dict[str, tuple[float, dict]] = {}
        self._batch_cache: tuple[float, dict[str, dict]] | None = None

    def is_configured(self) -> bool:
        return bool(self._api_key)

    async def fetch_quote(self, symbol: str) -> dict | None:
        """Fetch a single crypto quote."""
        clean = self._normalize_symbol(symbol)
        now = time.time()
        cached = self._cache.get(clean)
        if cached and (now - cached[0]) < CACHE_TTL:
            return cached[1]

        result = await self.fetch_quotes([symbol])
        return result.get(symbol) or result.get(clean)

    async def fetch_quotes(self, symbols: list[str]) -> dict[str, dict]:
        """Batch-fetch crypto quotes. CMC supports up to 100 symbols per call."""
        if not self._api_key:
            return {}

        now = time.time()
        if self._batch_cache and (now - self._batch_cache[0]) < CACHE_TTL:
            cached = self._batch_cache[1]
            hit = {s: cached[self._normalize_symbol(s)] for s in symbols
                   if self._normalize_symbol(s) in cached}
            if len(hit) == len(symbols):
                return hit

        clean_map: dict[str, str] = {}
        for s in symbols:
            clean_map[self._normalize_symbol(s)] = s

        slug_list = ",".join(clean_map.keys())

        try:
            data = await asyncio.wait_for(
                asyncio.to_thread(self._fetch_sync, slug_list), timeout=REQUEST_TIMEOUT
            )
        except asyncio.TimeoutError:
            logger.debug("[cmc] Timeout fetching quotes")
            return {}
        except Exception as exc:
            logger.debug("[cmc] Fetch failed: %s", exc)
            return {}

        if not data:
            return {}

        results: dict[str, dict] = {}
        for clean_sym, original_sym in clean_map.items():
            info = data.get(clean_sym.upper())
            if info:
                quote_usd = info.get("quote", {}).get("USD", {})
                parsed = {
                    "symbol": original_sym,
                    "name": info.get("name", ""),
                    "price": quote_usd.get("price", 0.0),
                    "change_24h": quote_usd.get("percent_change_24h", 0.0),
                    "market_cap": quote_usd.get("market_cap", 0.0),
                    "volume_24h": quote_usd.get("volume_24h", 0.0),
                    "source": "coinmarketcap",
                }
                results[original_sym] = parsed
                self._cache[clean_sym] = (now, parsed)

        self._batch_cache = (now, {self._normalize_symbol(k): v for k, v in results.items()})
        return results

    def _fetch_sync(self, symbol_csv: str) -> dict | None:
        import requests

        url = f"{API_BASE}/v1/cryptocurrency/quotes/latest"
        headers = {"X-CMC_PRO_API_KEY": self._api_key, "Accept": "application/json"}
        params = {"symbol": symbol_csv, "convert": "USD"}

        resp = requests.get(url, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            logger.debug("[cmc] HTTP %d: %s", resp.status_code, resp.text[:200])
            return None

        body = resp.json()
        if body.get("status", {}).get("error_code", 0) != 0:
            logger.debug("[cmc] API error: %s", body.get("status", {}).get("error_message"))
            return None

        return body.get("data", {})

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        """Convert 'BTC/USD' -> 'BTC', 'ETH/USD' -> 'ETH'."""
        s = symbol.strip().upper()
        if "/" in s:
            s = s.split("/")[0]
        return s
