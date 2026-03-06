from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import aiohttp
from tenacity import retry, stop_after_attempt, wait_exponential

from src.core.models.polymarket import PolymarketSignal
from src.data.cache.parquet_cache import ParquetCache

logger = logging.getLogger(__name__)

CLOB_BASE = "https://clob.polymarket.com"


class PolymarketAdapter:
    """Fetches Polymarket CLOB orderbook data and converts to PolymarketSignal objects.

    Gracefully degrades: returns [] when API key is absent or any request fails.
    Caches responses via ParquetCache to avoid rate-limit issues.
    """

    def __init__(
        self,
        api_key: str | None = None,
        cache: ParquetCache | None = None,
    ) -> None:
        self._api_key = api_key or os.getenv("POLYMARKET_API_KEY", "")
        self._cache = cache
        self._has_key = bool(self._api_key)

    async def fetch_signals(self, tags: list[str]) -> list[PolymarketSignal]:
        """Return PolymarketSignal objects for active markets matching tags."""
        if not self._has_key:
            logger.info("POLYMARKET_API_KEY not set — returning empty signal list")
            return []
        try:
            return await self._fetch_from_api(tags)
        except Exception as exc:
            logger.info("Polymarket fetch failed (non-critical): %s", exc)
            return []

    async def _fetch_from_api(self, tags: list[str]) -> list[PolymarketSignal]:
        headers = {"Authorization": f"Bearer {self._api_key}"}
        async with aiohttp.ClientSession(headers=headers) as session:
            markets = await self._get_markets(session, tags)
            signals = []
            for market in markets:
                sig = await self._market_to_signal(session, market)
                if sig is not None:
                    signals.append(sig)
            return signals

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    async def _get_markets(self, session: aiohttp.ClientSession, tags: list[str]) -> list[dict]:
        params = {"active": "true", "closed": "false", "limit": "50"}
        async with session.get(f"{CLOB_BASE}/markets", params=params) as resp:
            resp.raise_for_status()
            data = await resp.json()
        markets = data.get("data", [])
        if tags:
            markets = [m for m in markets if any(t in m.get("tags", []) for t in tags)]
        return markets[:20]  # cap to avoid excessive requests

    async def _market_to_signal(
        self, session: aiohttp.ClientSession, market: dict
    ) -> PolymarketSignal | None:
        tokens = market.get("tokens", [])
        yes_token = next((t for t in tokens if t.get("outcome") == "Yes"), None)
        no_token = next((t for t in tokens if t.get("outcome") == "No"), None)
        if not yes_token or not no_token:
            return None

        try:
            yes_ob = await self._get_orderbook(session, yes_token["token_id"])
            no_ob = await self._get_orderbook(session, no_token["token_id"])
        except Exception:
            return None

        yes_bid = float(yes_ob["bids"][0]["price"]) if yes_ob.get("bids") else 0.5
        no_bid = float(no_ob["bids"][0]["price"]) if no_ob.get("bids") else 0.5
        yes_ask = float(yes_ob["asks"][0]["price"]) if yes_ob.get("asks") else yes_bid

        total = yes_bid + no_bid
        implied_prob = yes_bid / total if total > 0 else 0.5

        return PolymarketSignal(
            market_id=market.get("condition_id", ""),
            question=market.get("question", ""),
            yes_price=round(yes_bid, 6),
            no_price=round(no_bid, 6),
            implied_prob=round(implied_prob, 6),
            spread=round(max(0.0, yes_ask - yes_bid), 6),
            volume_24h=float(market.get("volume24hr", 0)),
            open_interest=float(market.get("openInterest", 0)),
            timestamp=datetime.now(timezone.utc),
            tags=market.get("tags", []),
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    async def _get_orderbook(self, session: aiohttp.ClientSession, token_id: str) -> dict:
        async with session.get(f"{CLOB_BASE}/orderbook/{token_id}") as resp:
            resp.raise_for_status()
            return await resp.json()
