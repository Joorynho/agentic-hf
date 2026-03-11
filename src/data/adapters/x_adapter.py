"""News feed adapter via direct RSS feeds.

Fetches macro-relevant headlines from financial news outlets across all
asset classes (equities, FX, crypto, commodities). Uses feedparser
against reliable RSS endpoints.

Returns both raw headline dicts (for dashboard News Feed display) and
NewsItem objects (for pod researcher consumption).

Headlines are stored persistently across cycles — the full history is
available to agents. The dashboard shows the latest 100.
"""
from __future__ import annotations

import asyncio
import hashlib
import html
import logging
import re
import socket
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from src.core.models.market import NewsItem

logger = logging.getLogger(__name__)

FEED_SOURCES: list[dict] = [
    # --- General Macro / Markets ---
    {"name": "Yahoo Finance",  "category": "Markets",      "url": "https://finance.yahoo.com/news/rssindex"},
    {"name": "CNBC Top News",  "category": "Markets",      "url": "https://www.cnbc.com/id/100003114/device/rss/rss.html"},
    {"name": "CNBC World",     "category": "Markets",      "url": "https://www.cnbc.com/id/100727362/device/rss/rss.html"},
    {"name": "MarketWatch",    "category": "Markets",      "url": "https://feeds.marketwatch.com/marketwatch/topstories/"},
    {"name": "ZeroHedge",      "category": "Markets",      "url": "https://feeds.feedburner.com/zerohedge/feed"},
    {"name": "Bloomberg",      "category": "Markets",      "url": "https://news.google.com/rss/search?q=site:bloomberg.com+finance&hl=en-US&gl=US&ceid=US:en"},
    {"name": "FT",             "category": "Markets",      "url": "https://news.google.com/rss/search?q=site:ft.com+economy&hl=en-US&gl=US&ceid=US:en"},
    {"name": "WSJ",            "category": "Markets",      "url": "https://news.google.com/rss/search?q=site:wsj.com+markets&hl=en-US&gl=US&ceid=US:en"},
    {"name": "Reuters Biz",    "category": "Markets",      "url": "https://news.google.com/rss/search?q=site:reuters.com+business&hl=en-US&gl=US&ceid=US:en"},

    # --- Central Banks / Macro Policy ---
    {"name": "Central Banks",  "category": "Central Bank", "url": "https://news.google.com/rss/search?q=federal+reserve+ECB+bank+of+england+rate+decision&hl=en-US&gl=US&ceid=US:en"},
    {"name": "Macro News",     "category": "Macro",        "url": "https://news.google.com/rss/search?q=macro+economy+federal+reserve+inflation&hl=en-US&gl=US&ceid=US:en"},
    {"name": "Fed Watch",      "category": "Central Bank", "url": "https://news.google.com/rss/search?q=fed+rate+cut+hike+FOMC+minutes+powell&hl=en-US&gl=US&ceid=US:en"},

    # --- Geopolitics / Trade ---
    {"name": "Geopolitics",    "category": "Geopolitics",  "url": "https://news.google.com/rss/search?q=geopolitics+sanctions+trade+war+tariff&hl=en-US&gl=US&ceid=US:en"},

    # --- FX / Currencies ---
    {"name": "FX News",        "category": "FX",           "url": "https://news.google.com/rss/search?q=forex+currency+dollar+euro+yen+exchange+rate&hl=en-US&gl=US&ceid=US:en"},
    {"name": "ForexLive",      "category": "FX",           "url": "https://news.google.com/rss/search?q=site:forexlive.com&hl=en-US&gl=US&ceid=US:en"},
    {"name": "DailyFX",        "category": "FX",           "url": "https://news.google.com/rss/search?q=site:dailyfx.com&hl=en-US&gl=US&ceid=US:en"},

    # --- Crypto ---
    {"name": "CoinDesk",       "category": "Crypto",       "url": "https://www.coindesk.com/arc/outboundfeeds/rss/"},
    {"name": "CoinTelegraph",  "category": "Crypto",       "url": "https://cointelegraph.com/rss"},
    {"name": "The Block",      "category": "Crypto",       "url": "https://www.theblock.co/rss.xml"},
    {"name": "Decrypt",        "category": "Crypto",       "url": "https://news.google.com/rss/search?q=site:decrypt.co+crypto&hl=en-US&gl=US&ceid=US:en"},

    # --- Commodities / Energy ---
    {"name": "Oil & Energy",   "category": "Commodities",  "url": "https://news.google.com/rss/search?q=crude+oil+OPEC+natural+gas+energy+prices&hl=en-US&gl=US&ceid=US:en"},
    {"name": "Gold & Metals",  "category": "Commodities",  "url": "https://news.google.com/rss/search?q=gold+silver+copper+precious+metals+prices&hl=en-US&gl=US&ceid=US:en"},
    {"name": "Agriculture",    "category": "Commodities",  "url": "https://news.google.com/rss/search?q=wheat+corn+soybean+agriculture+commodity+prices&hl=en-US&gl=US&ceid=US:en"},
    {"name": "Kitco",          "category": "Commodities",  "url": "https://news.google.com/rss/search?q=site:kitco.com+gold&hl=en-US&gl=US&ceid=US:en"},
    {"name": "OilPrice",       "category": "Commodities",  "url": "https://news.google.com/rss/search?q=site:oilprice.com&hl=en-US&gl=US&ceid=US:en"},
]

BULLISH_WORDS = [
    "rally", "surge", "breakout", "bullish", "upside", "beat", "strong",
    "growth", "soar", "boom", "gain", "record high", "all-time high",
    "recovery", "optimism", "dovish", "easing", "stimulus", "upgrade",
    "outperform", "accelerat", "expand", "positive", "green",
]

BEARISH_WORDS = [
    "crash", "plunge", "bearish", "downside", "miss", "weak", "recession",
    "crisis", "collapse", "sell-off", "selloff", "tumble", "slump", "drop",
    "decline", "fear", "hawkish", "tightening", "downgrade", "default",
    "underperform", "contract", "negative", "red", "warning", "risk",
    "inflation surge", "rate hike", "layoff", "bankruptcy",
]

COOLDOWN = timedelta(minutes=5)
DASHBOARD_LIMIT = 100


class XAdapter:
    """Fetches macro-relevant headlines from direct news RSS feeds.

    Returns a tuple of (raw_headline_dicts, NewsItem_list). The raw dicts
    power the continuous dashboard News Feed; the NewsItems feed into pod
    researchers for analysis.

    Full history is stored persistently (not windowed) — agents can access
    all headlines from the current session including previous cycles.
    The dashboard display is capped at the latest 100.
    """

    def __init__(
        self,
        feeds: list[dict] | None = None,
        **_kwargs,
    ) -> None:
        self._feeds = feeds or list(FEED_SOURCES)
        self._cache_news: list[NewsItem] = []
        self._last_fetch: datetime | None = None

        self._all_headlines: list[dict] = []
        self._seen_hashes: set[str] = set()
        self._feed_health: dict[str, int] = {}

    async def fetch_tweets(self) -> tuple[list[dict], list[NewsItem]]:
        """Return (raw_headline_dicts, NewsItem_list) for dashboard + agents.

        The raw list is the full session history (sorted newest-first).
        """
        now = datetime.now(timezone.utc)
        if self._last_fetch and (now - self._last_fetch) < COOLDOWN:
            return list(self._all_headlines), list(self._cache_news)

        try:
            raw_items = await asyncio.wait_for(
                asyncio.to_thread(self._fetch_all_sync), timeout=45.0
            )

            self._merge_into_history(raw_items)
            self._cache_news = [self._to_newsitem(t) for t in self._all_headlines]
            self._last_fetch = now

            logger.info(
                "[news] Fetched %d new headlines from %d feeds, total stored=%d",
                len(raw_items), len(self._feeds), len(self._all_headlines),
            )
            return list(self._all_headlines), list(self._cache_news)

        except asyncio.TimeoutError:
            logger.info("[news] Fetch timed out — returning cached results")
            return list(self._all_headlines), list(self._cache_news)
        except Exception as exc:
            logger.info("[news] Fetch failed (non-critical): %s", exc)
            return list(self._all_headlines), list(self._cache_news)

    def get_dashboard_headlines(self) -> list[dict]:
        """Return the latest 100 headlines for dashboard display."""
        return self._all_headlines[:DASHBOARD_LIMIT]

    def _fetch_all_sync(self) -> list[dict]:
        """Synchronous fetch across all RSS feeds (runs in thread pool)."""
        import feedparser

        old_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(10)

        all_items: list[dict] = []
        try:
            for feed_cfg in self._feeds:
                name = feed_cfg["name"]
                url = feed_cfg["url"]
                category = feed_cfg.get("category", "Markets")
                try:
                    feed = feedparser.parse(
                        url,
                        request_headers={
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                            "Accept": "application/rss+xml, application/xml, text/xml, */*",
                        },
                    )
                    if feed.entries:
                        self._feed_health[name] = 0
                        for entry in feed.entries[:15]:
                            item = self._parse_entry(entry, name, category)
                            if item:
                                all_items.append(item)
                    else:
                        self._feed_health[name] = self._feed_health.get(name, 0) + 1
                        logger.debug("[news] Feed %s returned 0 entries", name)

                except Exception as exc:
                    self._feed_health[name] = self._feed_health.get(name, 0) + 1
                    logger.debug("[news] Feed %s error: %s", name, exc)

        finally:
            socket.setdefaulttimeout(old_timeout)

        all_items.sort(key=lambda t: t["timestamp"], reverse=True)
        return all_items

    def _parse_entry(self, entry: object, source_name: str, category: str) -> dict | None:
        """Convert a feedparser entry to a raw headline dict."""
        title = getattr(entry, "title", "") or ""
        if not title:
            return None

        dhash = hashlib.sha256(
            (source_name + title[:120]).encode()
        ).hexdigest()[:16]
        if dhash in self._seen_hashes:
            return None
        self._seen_hashes.add(dhash)

        summary = self._clean_html(
            getattr(entry, "summary", "") or getattr(entry, "description", "") or ""
        )
        text = self._clean_html(title)
        if summary and summary != text:
            text = text + " — " + summary[:300]

        link = getattr(entry, "link", "") or ""
        ts = self._parse_timestamp(entry)

        sentiment = self._compute_sentiment(text)
        if sentiment > 0.1:
            sentiment_label = "bullish"
        elif sentiment < -0.1:
            sentiment_label = "bearish"
        else:
            sentiment_label = "neutral"

        return {
            "username": source_name,
            "text": text[:500],
            "timestamp": ts.isoformat(),
            "url": link,
            "sentiment": round(sentiment, 3),
            "sentiment_label": sentiment_label,
            "category": category,
            "dedupe_hash": dhash,
        }

    def _merge_into_history(self, new_items: list[dict]) -> None:
        """Merge new items into full session history (no window cutoff)."""
        existing_hashes = {t["dedupe_hash"] for t in self._all_headlines}

        added = 0
        for item in new_items:
            if item["dedupe_hash"] not in existing_hashes:
                self._all_headlines.append(item)
                existing_hashes.add(item["dedupe_hash"])
                added += 1

        self._all_headlines.sort(key=lambda t: t["timestamp"], reverse=True)

        if len(self._seen_hashes) > 10000:
            self._seen_hashes = set(list(self._seen_hashes)[-5000:])

        if added:
            logger.debug("[news] Added %d new headlines, total=%d", added, len(self._all_headlines))

    @staticmethod
    def _to_newsitem(item: dict) -> NewsItem:
        """Convert a raw headline dict to a NewsItem for the agent pipeline."""
        try:
            ts = datetime.fromisoformat(item["timestamp"])
        except (ValueError, TypeError):
            ts = datetime.now(timezone.utc)

        dhash = item.get("dedupe_hash", hashlib.sha256(
            item.get("url", "").encode()
        ).hexdigest()[:16])

        return NewsItem(
            timestamp=ts,
            source=f"news:{item['username']}",
            headline=item["text"][:200],
            url=item.get("url", ""),
            body_snippet=item["text"][:500],
            entities=[],
            sentiment=max(-1.0, min(1.0, item.get("sentiment", 0.0))),
            event_tags=["news", item.get("category", "Markets").lower()],
            reliability_score=0.6,
            dedupe_hash=dhash,
        )

    @staticmethod
    def _compute_sentiment(text: str) -> float:
        """Keyword-based sentiment scoring, clamped to [-1, +1]."""
        lower = text.lower()
        bullish = sum(1 for w in BULLISH_WORDS if w in lower)
        bearish = sum(1 for w in BEARISH_WORDS if w in lower)
        total = bullish + bearish
        if total == 0:
            return 0.0
        return max(-1.0, min(1.0, (bullish - bearish) / total))

    @staticmethod
    def _clean_html(raw: str) -> str:
        """Strip HTML tags and decode entities from RSS content."""
        text = re.sub(r"<[^>]+>", " ", raw)
        text = html.unescape(text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def _parse_timestamp(entry: object) -> datetime:
        for attr in ("published", "updated"):
            raw = getattr(entry, attr, None)
            if raw:
                try:
                    return parsedate_to_datetime(raw).astimezone(timezone.utc)
                except (ValueError, TypeError):
                    pass
        return datetime.now(timezone.utc)

    def get_active_accounts(self) -> int:
        """Count of feed sources configured."""
        return len(self._feeds)

    def get_healthy_instances(self) -> int:
        """Count of feeds that are currently responding."""
        return sum(
            1 for name in [f["name"] for f in self._feeds]
            if self._feed_health.get(name, 0) < 3
        )
