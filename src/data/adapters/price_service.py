"""PriceService — single entry point for live quotes across all asset classes.

Routes to the right adapter based on symbol type, with fallback to Alpha Vantage.
Pods never call CoinMarketCap or StockPrices.dev directly — always go through here.
"""
from __future__ import annotations

import logging

from src.data.adapters.stockprices_adapter import StockPricesAdapter
from src.data.adapters.coinmarketcap_adapter import CoinMarketCapAdapter
from src.data.adapters.alphavantage_adapter import AlphaVantageAdapter

logger = logging.getLogger(__name__)

CRYPTO_TICKERS = frozenset([
    "BTC", "ETH", "SOL", "ADA", "XRP", "DOT", "LTC", "AVAX",
    "AAVE", "UNI", "SUSHI", "CRV", "LDO", "LINK", "GRT",
    "DOGE", "SHIB", "PEPE", "BONK", "WIF", "TRUMP",
    "FIL", "RENDER", "ARB", "ONDO", "POL",
    "BAT", "BCH", "HYPE", "PAXG", "SKY", "XTZ", "YFI",
])


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
        self._log_status()

    def _log_status(self) -> None:
        sources = ["StockPrices.dev"]
        if self._cmc.is_configured():
            sources.append("CoinMarketCap")
        if self._av.is_configured():
            sources.append("AlphaVantage")
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
            return await self._av.fetch_crypto_quote(symbol)
        return None

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

        return results

    @staticmethod
    def _is_crypto(symbol: str) -> bool:
        if "/" in symbol:
            return True
        return symbol.upper() in CRYPTO_TICKERS
