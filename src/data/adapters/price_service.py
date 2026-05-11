"""PriceService — single entry point for live quotes across all asset classes.

Routes to the right adapter based on symbol type, with fallback to Alpha Vantage.
Pods never call CoinMarketCap or StockPrices.dev directly — always go through here.
"""
from __future__ import annotations

import asyncio
import logging
import math
import time

from src.data.adapters.stockprices_adapter import StockPricesAdapter
from src.data.adapters.coinmarketcap_adapter import CoinMarketCapAdapter
from src.data.adapters.alphavantage_adapter import AlphaVantageAdapter

logger = logging.getLogger(__name__)
YFINANCE_CACHE_TTL = 30.0
YFINANCE_TIMEOUT = 8.0

CRYPTO_TICKERS = frozenset([
    "BTC", "ETH", "SOL", "ADA", "XRP", "DOT", "LTC", "AVAX",
    "AAVE", "UNI", "SUSHI", "CRV", "LDO", "LINK", "GRT",
    "DOGE", "SHIB", "PEPE", "BONK", "WIF", "TRUMP",
    "FIL", "RENDER", "ARB", "ONDO", "POL",
    "BAT", "BCH", "HYPE", "PAXG", "SKY", "XTZ", "YFI",
])
CRYPTO_QUOTES = ("USDT", "USDC", "USD", "BTC")


def crypto_base_symbol(symbol: str) -> str:
    """Return the crypto base ticker from ETH/USD, ETH-USD, or ETHUSD."""
    s = str(symbol or "").strip().upper().replace("-", "/")
    if "/" in s:
        return s.split("/", 1)[0]
    for quote in CRYPTO_QUOTES:
        if s.endswith(quote) and len(s) > len(quote):
            base = s[: -len(quote)]
            if base in CRYPTO_TICKERS:
                return base
    return s


def is_crypto_symbol(symbol: str) -> bool:
    """Return True when the symbol is one of our supported crypto forms."""
    s = str(symbol or "").strip().upper()
    if "/" in s or "-" in s:
        base = crypto_base_symbol(s)
        return base in CRYPTO_TICKERS
    return crypto_base_symbol(s) in CRYPTO_TICKERS


def canonical_crypto_symbol(symbol: str) -> str:
    """Return the dashboard/accountant canonical crypto pair form."""
    base = crypto_base_symbol(symbol)
    return f"{base}/USD" if base in CRYPTO_TICKERS else str(symbol or "").strip().upper()


def yfinance_crypto_symbol(symbol: str) -> str:
    """Return Yahoo's crypto pair form (ETH-USD)."""
    base = crypto_base_symbol(symbol)
    return f"{base}-USD" if base in CRYPTO_TICKERS else str(symbol or "").strip().upper()


def symbol_aliases(symbol: str) -> set[str]:
    """Return common broker/feed aliases for matching the same instrument."""
    s = str(symbol or "").strip().upper()
    if not s:
        return set()
    aliases = {s, s.replace("-", "/"), s.replace("/", "-"), s.replace("/", ""), s.replace("-", "")}
    if is_crypto_symbol(s):
        base = crypto_base_symbol(s)
        aliases.update({base, f"{base}/USD", f"{base}-USD", f"{base}USD"})
    return {a for a in aliases if a}


class PriceService:
    """Aggregates live price sources with automatic routing and fallback."""

    def __init__(
        self,
        stockprices: StockPricesAdapter | None = None,
        coinmarketcap: CoinMarketCapAdapter | None = None,
        alphavantage: AlphaVantageAdapter | None = None,
    ) -> None:
        self._spd = stockprices or StockPricesAdapter()
        self._cmc = coinmarketcap or CoinMarketCapAdapter()
        self._av = alphavantage or AlphaVantageAdapter()
        self._yf_crypto_cache: dict[str, tuple[float, dict]] = {}
        self._log_status()

    def _log_status(self) -> None:
        sources = ["StockPrices.dev"]
        if self._cmc.is_configured():
            sources.append("CoinMarketCap")
        if self._av.is_configured():
            sources.append("AlphaVantage")
        sources.append("YahooFinance crypto fallback")
        logger.info("[price-service] Active sources: %s", ", ".join(sources))

    async def get_quote(self, symbol: str) -> dict | None:
        """Get a single live quote with fallback."""
        if self._is_crypto(symbol):
            return await self._get_crypto_quote(symbol)
        return await self._get_stock_quote(symbol)

    async def get_quotes(self, symbols: list[str]) -> dict[str, dict]:
        """Batch-fetch live quotes for a list of symbols."""
        crypto_syms = [s for s in symbols if self._is_crypto(s)]
        stock_syms = [s for s in symbols if not self._is_crypto(s)]

        results: dict[str, dict] = {}

        if crypto_syms:
            crypto_results = await self._get_crypto_quotes_batch(crypto_syms)
            results.update(crypto_results)

        if stock_syms:
            stock_results = await self._get_stock_quotes_batch(stock_syms)
            results.update(stock_results)

        return results

    async def _get_stock_quote(self, symbol: str) -> dict | None:
        quote = await self._spd.fetch_quote(symbol)
        if quote:
            return quote

        if self._av.is_configured():
            logger.debug("[price-service] StockPrices.dev failed for %s, trying AlphaVantage", symbol)
            return await self._av.fetch_quote(symbol)
        return None

    async def _get_crypto_quote(self, symbol: str) -> dict | None:
        if self._cmc.is_configured():
            quote = await self._cmc.fetch_quote(symbol)
            if quote:
                return quote

        if self._av.is_configured():
            logger.debug("[price-service] CMC failed for %s, trying AlphaVantage", symbol)
            quote = await self._av.fetch_crypto_quote(symbol)
            if quote:
                return quote

        return await self._get_yfinance_crypto_quote(symbol)

    async def _get_stock_quotes_batch(self, symbols: list[str]) -> dict[str, dict]:
        results = await self._spd.fetch_quotes(symbols)
        missing = [s for s in symbols if s not in results]

        if missing and self._av.is_configured():
            logger.debug("[price-service] Falling back to AlphaVantage for %d stock symbols", len(missing))
            av_results = await self._av.fetch_quotes(missing)
            results.update(av_results)

        return results

    async def _get_crypto_quotes_batch(self, symbols: list[str]) -> dict[str, dict]:
        results: dict[str, dict] = {}

        if self._cmc.is_configured():
            results = await self._cmc.fetch_quotes(symbols)

        missing = [s for s in symbols if s not in results]
        if missing and self._av.is_configured():
            logger.debug("[price-service] Falling back to AlphaVantage for %d crypto symbols", len(missing))
            av_results = await self._av.fetch_quotes(missing)
            results.update(av_results)

        missing = [s for s in symbols if s not in results]
        if missing:
            yf_results = await self._get_yfinance_crypto_quotes(missing)
            results.update(yf_results)

        return results

    async def _get_yfinance_crypto_quote(self, symbol: str) -> dict | None:
        quotes = await self._get_yfinance_crypto_quotes([symbol])
        return quotes.get(symbol)

    async def _get_yfinance_crypto_quotes(self, symbols: list[str]) -> dict[str, dict]:
        """No-key crypto fallback using Yahoo's dashed pair symbols."""
        results: dict[str, dict] = {}
        now = time.time()
        for symbol in symbols:
            canonical = canonical_crypto_symbol(symbol)
            cached = self._yf_crypto_cache.get(canonical)
            if cached and (now - cached[0]) < YFINANCE_CACHE_TTL:
                results[symbol] = dict(cached[1], symbol=symbol)
                continue
            try:
                quote = await asyncio.wait_for(
                    asyncio.to_thread(self._fetch_yfinance_crypto_sync, canonical),
                    timeout=YFINANCE_TIMEOUT,
                )
            except asyncio.TimeoutError:
                logger.debug("[price-service] yfinance crypto timeout for %s", symbol)
                quote = None
            except Exception as exc:
                logger.debug("[price-service] yfinance crypto failed for %s: %s", symbol, exc)
                quote = None
            if quote:
                cached_quote = dict(quote, symbol=canonical)
                self._yf_crypto_cache[canonical] = (now, cached_quote)
                results[symbol] = dict(quote, symbol=symbol)
        return results

    def _fetch_yfinance_crypto_sync(self, canonical_symbol: str) -> dict | None:
        """Fetch one crypto quote from yfinance. Kept sync for to_thread."""
        import yfinance as yf

        yf_symbol = yfinance_crypto_symbol(canonical_symbol)
        ticker = yf.Ticker(yf_symbol)
        price = None
        previous_close = None

        try:
            fast = getattr(ticker, "fast_info", {}) or {}
            if hasattr(fast, "get"):
                price = fast.get("last_price") or fast.get("regular_market_price")
                previous_close = fast.get("previous_close")
        except Exception:
            price = None

        if not price:
            hist = ticker.history(period="1d", interval="1m", auto_adjust=False)
            if hist is not None and not hist.empty:
                price = float(hist["Close"].dropna().iloc[-1])
                if len(hist["Close"].dropna()) > 1:
                    previous_close = float(hist["Close"].dropna().iloc[0])

        try:
            price = float(price) if price is not None else 0.0
        except Exception:
            price = 0.0
        if not math.isfinite(price) or price <= 0:
            return None

        change_amount = 0.0
        change_pct = 0.0
        try:
            previous = float(previous_close or 0.0)
            if previous > 0:
                change_amount = price - previous
                change_pct = change_amount / previous * 100.0
        except Exception:
            pass

        return {
            "symbol": canonical_symbol,
            "name": crypto_base_symbol(canonical_symbol),
            "price": price,
            "change_amount": change_amount,
            "change_pct": change_pct,
            "source": "yfinance",
        }

    @staticmethod
    def _is_crypto(symbol: str) -> bool:
        return is_crypto_symbol(symbol)
