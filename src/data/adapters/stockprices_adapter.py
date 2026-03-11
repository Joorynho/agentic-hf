"""StockPrices.dev adapter — zero-auth real-time stock/ETF quotes.

Endpoints:
  GET https://stockprices.dev/api/stocks/:ticker
  GET https://stockprices.dev/api/etfs/:ticker

No API key required. No documented rate limit.
"""
from __future__ import annotations

import asyncio
import logging
import time

logger = logging.getLogger(__name__)

BASE_URL = "https://stockprices.dev/api"
CACHE_TTL = 30.0
REQUEST_TIMEOUT = 5

KNOWN_ETFS = frozenset([
    "SPY", "QQQ", "IWM", "DIA", "VTI", "VOO", "RSP", "MDY",
    "XLF", "XLE", "XLK", "XLV", "XLI", "XLP", "XLU", "XLY", "XLC", "XLB", "XLRE",
    "ARKK", "SOXX", "SMH", "TAN", "LIT", "HACK", "IBB", "XBI",
    "KWEB", "CQQQ", "ICLN", "QCLN", "BOTZ", "ROBO",
    "EFA", "EEM", "VGK", "EWJ", "FXI", "EWZ", "INDA", "EWT", "EWY", "VWO",
    "IEMG", "MCHI", "TLT", "IEF", "SHY", "HYG", "LQD", "AGG", "BND", "TIP",
    "EMB", "JNK", "FXE", "FXY", "FXB", "FXA", "FXC", "FXF", "UUP", "UDN",
    "CEW", "USDU", "EWG", "EWU", "EWQ", "EWP", "EWI", "EWN", "EWL", "EWA",
    "EWC", "EWS", "EWM", "EWW", "EWH", "THD", "VNM", "EIDO", "EPHE",
    "BWX", "IGOV", "LEMB", "EMLC", "FM",
    "GLD", "IAU", "GDX", "GDXJ", "SGOL", "SLV", "PSLV", "SIL",
    "USO", "XOP", "OIH", "UNG", "AMLP", "DBA", "CORN", "WEAT", "SOYB",
    "MOO", "COW", "GSG", "PDBC", "COM", "DJP", "COMT", "CPER", "COPX",
    "DBB", "PICK", "URA", "URNM", "BATT", "XME", "REMX",
])


class StockPricesAdapter:
    """Fetches real-time stock/ETF quotes from StockPrices.dev."""

    def __init__(self) -> None:
        self._cache: dict[str, tuple[float, dict]] = {}

    async def fetch_quote(self, symbol: str) -> dict | None:
        """Fetch a single quote. Returns None on failure."""
        now = time.time()
        cached = self._cache.get(symbol)
        if cached and (now - cached[0]) < CACHE_TTL:
            return cached[1]

        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(self._fetch_sync, symbol), timeout=REQUEST_TIMEOUT
            )
            if result:
                self._cache[symbol] = (now, result)
            return result
        except asyncio.TimeoutError:
            logger.debug("[stockprices] Timeout fetching %s", symbol)
            return cached[1] if cached else None
        except Exception as exc:
            logger.debug("[stockprices] Failed to fetch %s: %s", symbol, exc)
            return cached[1] if cached else None

    async def fetch_quotes(self, symbols: list[str]) -> dict[str, dict]:
        """Fetch quotes for multiple symbols (sequential, cached)."""
        results: dict[str, dict] = {}
        for symbol in symbols:
            quote = await self.fetch_quote(symbol)
            if quote:
                results[symbol] = quote
        return results

    def _fetch_sync(self, symbol: str) -> dict | None:
        import requests

        endpoint = "etfs" if symbol.upper() in KNOWN_ETFS else "stocks"
        url = f"{BASE_URL}/{endpoint}/{symbol.upper()}"

        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            logger.debug("[stockprices] HTTP %d for %s", resp.status_code, symbol)
            return None

        data = resp.json()
        return {
            "symbol": data.get("Ticker", symbol),
            "name": data.get("Name", ""),
            "price": data.get("Price", 0.0),
            "change_amount": data.get("ChangeAmount", 0.0),
            "change_pct": data.get("ChangePercentage", 0.0),
            "source": "stockprices.dev",
        }
