from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone

from src.core.models.market import NewsItem
from src.data.adapters.sentiment import compute_keyword_sentiment

logger = logging.getLogger(__name__)

FINANCE_KEYWORDS = ["economy", "federal reserve", "interest rate", "inflation",
                    "GDP", "earnings", "stock market", "treasury", "trade war",
                    "recession", "oil price", "unemployment"]

COOLDOWN = timedelta(minutes=5)
MAX_ARTICLES = 75


class GdeltAdapter:
    """Fetches recent finance/economy articles from the GDELT DOC 2.0 API.

    Returns a list of NewsItem objects. Rate-limited to one fetch per 5 minutes
    via an in-memory cooldown timer. Gracefully returns [] on failure.
    No API key required — GDELT is a free, open dataset.
    """

    def __init__(self, keywords: list[str] | None = None) -> None:
        self._keywords = keywords or FINANCE_KEYWORDS
        self._cache: list[NewsItem] = []
        self._last_fetch: datetime | None = None
        self._seen_hashes: set[str] = set()

    async def fetch_articles(self) -> list[NewsItem]:
        """Return recent finance-related NewsItem objects from GDELT."""
        import asyncio

        now = datetime.now(timezone.utc)
        if self._last_fetch and (now - self._last_fetch) < COOLDOWN:
            return list(self._cache)

        try:
            articles = await asyncio.wait_for(
                asyncio.to_thread(self._fetch_sync), timeout=12.0
            )
            self._cache = articles
            self._last_fetch = now
            logger.info("[gdelt] Fetched %d articles", len(articles))
            return list(articles)
        except asyncio.TimeoutError:
            logger.info("[gdelt] Fetch timed out — returning cached results")
            return list(self._cache)
        except Exception as exc:
            logger.info("[gdelt] Fetch failed (non-critical): %s", exc)
            return list(self._cache)

    def _fetch_sync(self) -> list[NewsItem]:
        import socket
        from gdeltdoc import Filters, GdeltDoc

        old_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(8)

        try:
            f = Filters(
                keyword=self._keywords,
                timespan="1d",
                num_records=MAX_ARTICLES,
                language="english",
            )

            gd = GdeltDoc()
            df = gd.article_search(f)
        finally:
            socket.setdefaulttimeout(old_timeout)

        if df is None or df.empty:
            return []

        items: list[NewsItem] = []
        now = datetime.now(timezone.utc)

        for _, row in df.iterrows():
            url = str(row.get("url", ""))
            title = str(row.get("title", ""))
            if not url or not title:
                continue

            dhash = hashlib.sha256(url.encode()).hexdigest()[:16]
            if dhash in self._seen_hashes:
                continue
            self._seen_hashes.add(dhash)

            seen_raw = row.get("seendate", "")
            try:
                ts = datetime.strptime(str(seen_raw)[:19], "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                ts = now

            domain = str(row.get("domain", "gdelt"))
            entities = self._extract_entities(title)

            tone_raw = row.get("tone")
            if tone_raw is not None:
                try:
                    tone_val = float(str(tone_raw).split(",")[0])
                    sentiment = max(-1.0, min(1.0, tone_val / 10.0))
                except (ValueError, TypeError, IndexError):
                    sentiment = compute_keyword_sentiment(title)
            else:
                sentiment = compute_keyword_sentiment(title)

            item = NewsItem(
                timestamp=ts,
                source=f"gdelt:{domain}",
                headline=title,
                body_snippet=title[:500],
                entities=entities,
                sentiment=sentiment,
                event_tags=["gdelt", "finance"],
                reliability_score=0.6,
                dedupe_hash=dhash,
            )
            items.append(item)

        if len(self._seen_hashes) > 5000:
            self._seen_hashes = set(list(self._seen_hashes)[-2500:])

        return items

    @staticmethod
    def _extract_entities(headline: str) -> list[str]:
        """Extract stock tickers and known entity names from a headline."""
        tickers = ["AAPL", "MSFT", "AMZN", "GOOGL", "META", "TSLA", "NVDA",
                    "SPY", "QQQ", "TLT", "GLD", "VIX"]
        found = []
        upper = headline.upper()
        for t in tickers:
            if t in upper:
                found.append(t)
        return found
