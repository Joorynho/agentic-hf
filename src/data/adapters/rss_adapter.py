from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from src.core.models.market import NewsItem

logger = logging.getLogger(__name__)

DEFAULT_FEEDS = [
    # --- Macro / General Finance ---
    "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114",
    "https://feeds.marketwatch.com/marketwatch/topstories/",
    "https://finance.yahoo.com/news/rssindex",
    "https://feeds.reuters.com/reuters/businessNews",
    # --- Crypto ---
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://cointelegraph.com/rss",
    "https://www.theblock.co/rss.xml",
]

CACHE_TTL = timedelta(minutes=10)
RELIABILITY_MAP = {
    "reuters.com": 0.9,
    "cnbc.com": 0.8,
    "marketwatch.com": 0.75,
    "yahoo.com": 0.7,
    "coindesk.com": 0.75,
    "cointelegraph.com": 0.7,
    "theblock.co": 0.75,
}


class RssAdapter:
    """Aggregates financial news from multiple RSS feeds.

    Returns a deduplicated list of NewsItem objects. Results are cached
    for 10 minutes. feedparser runs in a thread pool since it's synchronous.
    Gracefully returns [] on failure.
    """

    def __init__(self, feed_urls: list[str] | None = None) -> None:
        self._feeds = feed_urls or DEFAULT_FEEDS
        self._cache: list[NewsItem] = []
        self._cache_ts: datetime | None = None
        self._seen_hashes: set[str] = set()

    async def fetch_news(self) -> list[NewsItem]:
        """Return recent financial news items from configured RSS feeds."""
        now = datetime.now(timezone.utc)
        if self._cache_ts and (now - self._cache_ts) < CACHE_TTL:
            return list(self._cache)

        try:
            items = await asyncio.wait_for(
                asyncio.to_thread(self._fetch_all_sync), timeout=12.0
            )
            self._cache = items
            self._cache_ts = now
            logger.info("[rss] Fetched %d articles from %d feeds", len(items), len(self._feeds))
            return list(items)
        except asyncio.TimeoutError:
            logger.info("[rss] Fetch timed out — returning cached results")
            return list(self._cache)
        except Exception as exc:
            logger.info("[rss] Fetch failed (non-critical): %s", exc)
            return list(self._cache)

    def _fetch_all_sync(self) -> list[NewsItem]:
        import socket
        import feedparser

        all_items: list[NewsItem] = []
        old_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(8)

        try:
            for url in self._feeds:
                try:
                    feed = feedparser.parse(url)
                    for entry in feed.entries[:30]:
                        item = self._entry_to_newsitem(entry, url)
                        if item:
                            all_items.append(item)
                except Exception as exc:
                    logger.debug("[rss] Feed %s failed: %s", url, exc)
        finally:
            socket.setdefaulttimeout(old_timeout)

        all_items.sort(key=lambda x: x.timestamp, reverse=True)

        if len(self._seen_hashes) > 5000:
            self._seen_hashes = set(list(self._seen_hashes)[-2500:])

        return all_items

    def _entry_to_newsitem(self, entry: dict, feed_url: str) -> NewsItem | None:
        link = getattr(entry, "link", "") or ""
        title = getattr(entry, "title", "") or ""
        if not link or not title:
            return None

        dhash = hashlib.sha256(link.encode()).hexdigest()[:16]
        if dhash in self._seen_hashes:
            return None
        self._seen_hashes.add(dhash)

        ts = self._parse_timestamp(entry)
        summary = getattr(entry, "summary", "") or ""
        snippet = (summary[:500] if summary else title[:500])
        domain = self._extract_domain(link)
        reliability = self._domain_reliability(domain)
        entities = self._extract_entities(title)

        return NewsItem(
            timestamp=ts,
            source=f"rss:{domain}",
            headline=title,
            url=link,
            body_snippet=snippet,
            entities=entities,
            sentiment=0.0,
            event_tags=["rss", "finance"],
            reliability_score=reliability,
            dedupe_hash=dhash,
        )

    @staticmethod
    def _parse_timestamp(entry: dict) -> datetime:
        for attr in ("published", "updated"):
            raw = getattr(entry, attr, None)
            if raw:
                try:
                    return parsedate_to_datetime(raw).astimezone(timezone.utc)
                except (ValueError, TypeError):
                    pass
        return datetime.now(timezone.utc)

    @staticmethod
    def _extract_domain(url: str) -> str:
        try:
            from urllib.parse import urlparse
            return urlparse(url).netloc.lower().lstrip("www.")
        except Exception:
            return "unknown"

    @staticmethod
    def _domain_reliability(domain: str) -> float:
        for key, score in RELIABILITY_MAP.items():
            if key in domain:
                return score
        return 0.5

    @staticmethod
    def _extract_entities(headline: str) -> list[str]:
        tickers = [
            "AAPL", "MSFT", "AMZN", "GOOGL", "META", "TSLA", "NVDA",
            "SPY", "QQQ", "TLT", "GLD", "VIX",
            "BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "DOT", "LTC", "AVAX",
        ]
        found = []
        upper = headline.upper()
        for t in tickers:
            if t in upper:
                found.append(t)
        return found
