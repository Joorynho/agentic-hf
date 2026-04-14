"""Shared research data ingestion service.

Fetches FRED macro data, Polymarket signals, RSS news, and X/news feeds once
per interval and stores results for all pod researchers to consume, eliminating
redundant parallel fetches across the 4 pods.

Each pod researcher still performs its own asset-class-specific LLM scoring
and macro score computation — only the raw external data fetch is centralised.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.data.adapters.fred_adapter import FredAdapter
    from src.data.adapters.polymarket_adapter import PolymarketAdapter
    from src.data.adapters.rss_adapter import RssAdapter
    from src.data.adapters.x_adapter import XAdapter

logger = logging.getLogger(__name__)

_DEFAULT_INTERVAL = 300  # 5 minutes


class ResearchIngestionService:
    """Background service that fetches shared research data at a fixed interval.

    Lifecycle:
        await service.start()   # kicks off background task, fetches immediately
        ...
        await service.stop()    # cancels background task

    Data access:
        service.fred_snapshot   # dict of FRED series → value
        service.poly_signals    # list of dicts (Polymarket signals)
        service.news_items      # list of dicts (serialised NewsItem models)
        service.x_feed          # list of raw tweet/news dicts
        service.is_fresh()      # True if fetched within max_age_seconds
    """

    def __init__(
        self,
        fred_adapter: Optional[FredAdapter] = None,
        polymarket_adapter: Optional[PolymarketAdapter] = None,
        rss_adapter: Optional[RssAdapter] = None,
        x_adapter: Optional[XAdapter] = None,
        interval_seconds: int = _DEFAULT_INTERVAL,
    ) -> None:
        self._fred = fred_adapter
        self._poly = polymarket_adapter
        self._rss = rss_adapter
        self._x = x_adapter
        self._interval = interval_seconds
        self._task: asyncio.Task | None = None

        # Shared data — updated in-place on every fetch cycle
        self.fred_snapshot: dict = {}
        self.poly_signals: list = []
        self.news_items: list = []
        self.x_feed: list = []
        self.last_fetch_time: datetime | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the background fetch loop (fetches immediately on start)."""
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._loop(), name="research_ingestion")
        logger.info(
            "[research_ingestion] Background service started (interval=%ds)", self._interval
        )

    async def stop(self) -> None:
        """Cancel the background task gracefully."""
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("[research_ingestion] Background service stopped")

    # ------------------------------------------------------------------
    # Background loop
    # ------------------------------------------------------------------

    async def _loop(self) -> None:
        """Fetch immediately on first call, then sleep and repeat."""
        while True:
            try:
                await self._fetch()
            except Exception as e:
                logger.warning("[research_ingestion] Fetch cycle error: %s", e)
            await asyncio.sleep(self._interval)

    async def _fetch(self) -> None:
        """Fetch all shared research data concurrently."""
        fred, poly, news, x_feed = await asyncio.gather(
            self._fetch_fred(),
            self._fetch_poly(),
            self._fetch_news(),
            self._fetch_x(),
            return_exceptions=True,
        )

        if not isinstance(fred, Exception):
            self.fred_snapshot = fred
        else:
            logger.debug("[research_ingestion] FRED fetch error: %s", fred)

        if not isinstance(poly, Exception):
            self.poly_signals = poly
        else:
            logger.debug("[research_ingestion] Polymarket fetch error: %s", poly)

        if not isinstance(news, Exception):
            self.news_items = news
        else:
            logger.debug("[research_ingestion] RSS fetch error: %s", news)

        if not isinstance(x_feed, Exception):
            self.x_feed = x_feed
        else:
            logger.debug("[research_ingestion] X feed fetch error: %s", x_feed)

        self.last_fetch_time = datetime.now(timezone.utc)
        logger.info(
            "[research_ingestion] Fetch complete: fred=%d keys, poly=%d signals, "
            "news=%d items, x=%d items",
            len(self.fred_snapshot),
            len(self.poly_signals),
            len(self.news_items),
            len(self.x_feed),
        )

    async def _fetch_fred(self) -> dict:
        if not self._fred:
            return self.fred_snapshot  # retain previous
        return await self._fred.fetch_snapshot()

    async def _fetch_poly(self) -> list:
        if not self._poly:
            return self.poly_signals
        raw = await self._poly.fetch_signals([])
        return [s.model_dump(mode="json") for s in raw]

    async def _fetch_news(self) -> list:
        if not self._rss:
            return self.news_items
        items = await self._rss.fetch_news()
        return [n.model_dump(mode="json") if hasattr(n, "model_dump") else n for n in items]

    async def _fetch_x(self) -> list:
        if not self._x:
            return self.x_feed
        feed, _ = await self._x.fetch_tweets()
        return feed

    # ------------------------------------------------------------------
    # Data access
    # ------------------------------------------------------------------

    def is_fresh(self, max_age_seconds: int = 600) -> bool:
        """Return True if data was fetched within max_age_seconds."""
        if self.last_fetch_time is None:
            return False
        return (datetime.now(timezone.utc) - self.last_fetch_time).total_seconds() < max_age_seconds

    def get_shared_data(self) -> dict:
        """Return current snapshot of all shared research data."""
        return {
            "fred_snapshot": self.fred_snapshot,
            "poly_signals": self.poly_signals,
            "news_items": self.news_items,
            "x_feed": self.x_feed,
            "last_fetch_time": self.last_fetch_time.isoformat() if self.last_fetch_time else None,
        }
