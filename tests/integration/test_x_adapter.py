"""Tests for XAdapter — news feed via direct RSS."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.data.adapters.x_adapter import (
    FEED_SOURCES,
    XAdapter,
)


def _make_feed_entry(title: str, link: str, published: str = "Mon, 09 Mar 2026 17:00:00 GMT"):
    """Create a mock feedparser entry."""
    return SimpleNamespace(
        title=title,
        link=link,
        summary=title,
        description=title,
        published=published,
        updated=None,
    )


def _make_feed(entries, bozo=False):
    """Create a mock feedparser result."""
    return SimpleNamespace(entries=entries, bozo=bozo)


class TestXAdapterInit:
    def test_defaults(self):
        adapter = XAdapter()
        assert adapter._feeds == list(FEED_SOURCES)
        assert len(adapter._all_headlines) == 0
        assert len(adapter._cache_news) == 0

    def test_custom_feeds(self):
        custom = [{"name": "Test", "category": "News", "url": "https://example.com/rss"}]
        adapter = XAdapter(feeds=custom)
        assert adapter._feeds == custom


class TestSentimentScoring:
    def test_bullish_text(self):
        from src.data.adapters.sentiment import compute_keyword_sentiment
        score = compute_keyword_sentiment("Markets surge to record high on strong growth data")
        assert score > 0

    def test_bearish_text(self):
        from src.data.adapters.sentiment import compute_keyword_sentiment
        score = compute_keyword_sentiment("Crash fears as recession deepens amid crisis")
        assert score < 0

    def test_neutral_text(self):
        from src.data.adapters.sentiment import compute_keyword_sentiment
        score = compute_keyword_sentiment("The meeting is scheduled for 3pm today")
        assert score == 0.0

    def test_mixed_text(self):
        from src.data.adapters.sentiment import compute_keyword_sentiment
        score = compute_keyword_sentiment("Rally fades into crash territory")
        assert -1.0 <= score <= 1.0

    def test_clamp_bounds(self):
        from src.data.adapters.sentiment import compute_keyword_sentiment
        score = compute_keyword_sentiment("surge rally breakout strong growth bullish")
        assert score <= 1.0
        score = compute_keyword_sentiment("crash plunge bearish recession crisis collapse")
        assert score >= -1.0


class TestParseEntry:
    def test_basic_parse(self):
        adapter = XAdapter()
        entry = _make_feed_entry(
            "Fed signals rate pause",
            "https://cnbc.com/article/123",
        )
        item = adapter._parse_entry(entry, "CNBC Top News", "Markets")
        assert item is not None
        assert item["username"] == "CNBC Top News"
        assert "Fed signals rate pause" in item["text"]
        assert item["sentiment_label"] in ("bullish", "bearish", "neutral")
        assert item["category"] == "Markets"

    def test_deduplication(self):
        adapter = XAdapter()
        entry = _make_feed_entry("Same headline", "https://example.com/1")
        first = adapter._parse_entry(entry, "Test Source", "Markets")
        second = adapter._parse_entry(entry, "Test Source", "Markets")
        assert first is not None
        assert second is None

    def test_empty_title_skipped(self):
        adapter = XAdapter()
        entry = _make_feed_entry("", "https://example.com/1")
        assert adapter._parse_entry(entry, "Test", "Markets") is None


class TestNewsItemConversion:
    def test_to_newsitem(self):
        item = {
            "username": "Bloomberg",
            "text": "Markets rally on earnings beat",
            "timestamp": "2026-03-09T17:00:00+00:00",
            "url": "https://bloomberg.com/article/123",
            "sentiment": 0.5,
            "sentiment_label": "bullish",
            "category": "Markets",
            "dedupe_hash": "abc123",
        }
        newsitem = XAdapter._to_newsitem(item)
        assert newsitem.source == "news:Bloomberg"
        assert newsitem.sentiment == 0.5
        assert "news" in newsitem.event_tags
        assert newsitem.dedupe_hash == "abc123"


class TestCacheTTL:
    @pytest.mark.asyncio
    async def test_returns_cache_within_cooldown(self):
        adapter = XAdapter()
        adapter._last_fetch = datetime.now(timezone.utc)
        adapter._all_headlines = [{"username": "cached", "text": "old", "timestamp": datetime.now(timezone.utc).isoformat(), "dedupe_hash": "x"}]
        adapter._cache_news = []

        raw, items = await adapter.fetch_tweets()
        assert len(raw) == 1
        assert raw[0]["username"] == "cached"


class TestGracefulFailure:
    @pytest.mark.asyncio
    async def test_timeout_returns_empty(self):
        adapter = XAdapter()

        with patch.object(adapter, "_fetch_all_sync", side_effect=Exception("network error")):
            adapter._last_fetch = None
            raw, items = await adapter.fetch_tweets()
            assert raw == []
            assert items == []


class TestBufferMerge:
    def test_merge_deduplication(self):
        adapter = XAdapter()
        now = datetime.now(timezone.utc)
        items = [
            {"username": "a", "text": "hello", "timestamp": now.isoformat(), "dedupe_hash": "h1"},
            {"username": "b", "text": "world", "timestamp": now.isoformat(), "dedupe_hash": "h2"},
        ]
        adapter._merge_into_history(items)
        assert len(adapter._all_headlines) == 2

        adapter._merge_into_history(items)
        assert len(adapter._all_headlines) == 2

    def test_history_persists_old_items(self):
        """Full session history is kept — old items are NOT evicted."""
        adapter = XAdapter()
        now = datetime.now(timezone.utc)
        old_time = (now - timedelta(hours=24)).isoformat()
        new_time = now.isoformat()

        adapter._all_headlines = [
            {"username": "old", "text": "stale", "timestamp": old_time, "dedupe_hash": "old1"},
        ]
        adapter._merge_into_history(
            [{"username": "new", "text": "fresh", "timestamp": new_time, "dedupe_hash": "new1"}],
        )
        usernames = [t["username"] for t in adapter._all_headlines]
        assert "new" in usernames
        assert "old" in usernames
        assert adapter._all_headlines[0]["username"] == "new"


class TestDashboardLimit:
    def test_dashboard_capped_at_100(self):
        adapter = XAdapter()
        now = datetime.now(timezone.utc)
        adapter._all_headlines = [
            {"username": f"src{i}", "text": f"headline {i}", "timestamp": now.isoformat(), "dedupe_hash": f"h{i}"}
            for i in range(150)
        ]
        dashboard = adapter.get_dashboard_headlines()
        assert len(dashboard) == 100
        assert len(adapter._all_headlines) == 150


class TestHealthTracking:
    def test_healthy_count(self):
        adapter = XAdapter()
        assert adapter.get_healthy_instances() == len(FEED_SOURCES)
        assert adapter.get_active_accounts() == len(FEED_SOURCES)


class TestSessionManagerInjection:
    @pytest.mark.asyncio
    async def test_x_adapter_injected_into_researchers(self):
        from unittest.mock import AsyncMock

        from src.core.bus.event_bus import EventBus
        from src.execution.paper.alpaca_adapter import AlpacaAdapter
        from src.mission_control.session_manager import SessionManager

        bus = EventBus()
        mock_alpaca = AsyncMock(spec=AlpacaAdapter)
        mock_alpaca.fetch_account = AsyncMock(
            return_value={"equity": 10000.0, "buying_power": 5000.0, "position_count": 0}
        )
        mock_alpaca.fetch_bars = AsyncMock(
            side_effect=lambda symbols, **kw: {s: [] for s in (symbols or [])}
        )

        manager = SessionManager(
            event_bus=bus,
            alpaca_adapter=mock_alpaca,
            enable_news_adapters=True,
        )
        await manager.start_live_session()

        for pod_id in ["equities", "fx", "crypto", "commodities"]:
            runtime = manager._pod_runtimes.get(pod_id)
            assert runtime is not None
            researcher = runtime._researcher
            assert hasattr(researcher, "x_adapter")
            assert isinstance(researcher.x_adapter, XAdapter)
