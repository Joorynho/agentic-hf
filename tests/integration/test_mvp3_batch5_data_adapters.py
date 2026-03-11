"""MVP3 Batch 5: FRED, GDELT, and RSS data adapter tests."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.models.market import NewsItem
from src.data.adapters.fred_adapter import FredAdapter
from src.data.adapters.gdelt_adapter import GdeltAdapter
from src.data.adapters.rss_adapter import RssAdapter


# ================================================================
#  FRED ADAPTER
# ================================================================


class TestFredAdapter:
    def test_init_without_key_returns_empty(self):
        adapter = FredAdapter(api_key="")
        assert adapter._has_key is False

    @pytest.mark.asyncio
    async def test_fetch_snapshot_no_key_returns_empty(self):
        adapter = FredAdapter(api_key="")
        result = await adapter.fetch_snapshot()
        assert result == {}

    @pytest.mark.asyncio
    async def test_fetch_snapshot_with_mock(self):
        adapter = FredAdapter(api_key="test_key")
        mock_snapshot = {"DFF": 5.33, "VIXCLS": 18.5, "T10Y2Y": 0.42}
        with patch.object(adapter, "_fetch_sync", return_value=mock_snapshot):
            result = await adapter.fetch_snapshot()
        assert result == mock_snapshot
        assert adapter._cache == mock_snapshot
        assert adapter._cache_ts is not None

    @pytest.mark.asyncio
    async def test_cache_ttl_prevents_refetch(self):
        adapter = FredAdapter(api_key="test_key")
        mock_snapshot = {"DFF": 5.33}
        with patch.object(adapter, "_fetch_sync", return_value=mock_snapshot) as mock_fn:
            await adapter.fetch_snapshot()
            await adapter.fetch_snapshot()
        mock_fn.assert_called_once()

    def test_extract_helper(self):
        snapshot = {"VIXCLS": 22.5, "DFF": 5.33}
        assert FredAdapter.extract(snapshot, "VIXCLS") == 22.5
        assert FredAdapter.extract(snapshot, "MISSING", 99.0) == 99.0


# ================================================================
#  GDELT ADAPTER
# ================================================================


class TestGdeltAdapter:
    @pytest.mark.asyncio
    async def test_fetch_articles_with_mock(self):
        import pandas as pd

        adapter = GdeltAdapter()
        mock_df = pd.DataFrame([
            {
                "url": "https://example.com/article1",
                "title": "Fed raises rates amid AAPL earnings",
                "seendate": "20260309T120000",
                "domain": "example.com",
                "language": "English",
                "sourcecountry": "US",
            },
            {
                "url": "https://example.com/article2",
                "title": "Global economy outlook for 2026",
                "seendate": "20260309T100000",
                "domain": "reuters.com",
                "language": "English",
                "sourcecountry": "US",
            },
        ])

        with patch("src.data.adapters.gdelt_adapter.GdeltAdapter._fetch_sync") as mock_fn:
            mock_fn.return_value = self._mock_items_from_df(mock_df, adapter)
            adapter._fetch_sync = mock_fn
            result = await adapter.fetch_articles()

        assert len(result) >= 1
        for item in result:
            assert isinstance(item, NewsItem)
            assert item.source.startswith("gdelt:")

    @pytest.mark.asyncio
    async def test_cooldown_prevents_refetch(self):
        adapter = GdeltAdapter()
        adapter._cache = [
            NewsItem(
                timestamp=datetime.now(timezone.utc),
                source="gdelt:test",
                headline="Test",
                body_snippet="Test article",
                dedupe_hash="abc123",
            )
        ]
        adapter._last_fetch = datetime.now(timezone.utc)

        result = await adapter.fetch_articles()
        assert len(result) == 1
        assert result[0].headline == "Test"

    def test_extract_entities(self):
        entities = GdeltAdapter._extract_entities("AAPL beats earnings, MSFT follows")
        assert "AAPL" in entities
        assert "MSFT" in entities

    @staticmethod
    def _mock_items_from_df(df, adapter):
        items = []
        for _, row in df.iterrows():
            item = NewsItem(
                timestamp=datetime.now(timezone.utc),
                source=f"gdelt:{row['domain']}",
                headline=row["title"],
                body_snippet=row["title"],
                entities=adapter._extract_entities(row["title"]),
                dedupe_hash=row["url"][:16],
            )
            items.append(item)
        return items


# ================================================================
#  RSS ADAPTER
# ================================================================


class TestRssAdapter:
    @pytest.mark.asyncio
    async def test_fetch_news_with_mock(self):
        adapter = RssAdapter(feed_urls=["https://test.com/rss"])
        mock_items = [
            NewsItem(
                timestamp=datetime.now(timezone.utc),
                source="rss:test.com",
                headline="Markets rally on Fed decision",
                body_snippet="The stock market surged today...",
                entities=["SPY"],
                dedupe_hash="test1234",
            )
        ]
        with patch.object(adapter, "_fetch_all_sync", return_value=mock_items):
            result = await adapter.fetch_news()

        assert len(result) == 1
        assert result[0].headline == "Markets rally on Fed decision"

    @pytest.mark.asyncio
    async def test_cache_ttl_prevents_refetch(self):
        adapter = RssAdapter(feed_urls=["https://test.com/rss"])
        adapter._cache = [
            NewsItem(
                timestamp=datetime.now(timezone.utc),
                source="rss:test",
                headline="Cached",
                body_snippet="Cached article",
                dedupe_hash="cached1",
            )
        ]
        adapter._cache_ts = datetime.now(timezone.utc)

        result = await adapter.fetch_news()
        assert len(result) == 1
        assert result[0].headline == "Cached"

    def test_extract_entities(self):
        entities = RssAdapter._extract_entities("NVDA surges past TSLA in market cap")
        assert "NVDA" in entities
        assert "TSLA" in entities

    def test_domain_reliability(self):
        assert RssAdapter._domain_reliability("reuters.com") == 0.9
        assert RssAdapter._domain_reliability("cnbc.com") == 0.8
        assert RssAdapter._domain_reliability("unknown-site.com") == 0.5


# ================================================================
#  SESSION MANAGER WIRING
# ================================================================


@pytest.mark.asyncio
async def test_session_manager_injects_adapters_into_researchers():
    """SessionManager creates all 4 pods with data adapters when enable_news_adapters=True.

    All pods (equities, fx, crypto, commodities) get polymarket, fred, rss, x adapters.
    """
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
        researcher = manager._pod_runtimes[pod_id]._researcher
        assert researcher.polymarket_adapter is not None
        assert researcher.fred_adapter is not None
        assert isinstance(researcher.fred_adapter, FredAdapter)
        assert researcher.rss_adapter is not None
        assert isinstance(researcher.rss_adapter, RssAdapter)


# ================================================================
#  RESEARCHER INTEGRATION
# ================================================================


@pytest.mark.asyncio
async def test_equities_researcher_with_mocked_adapters():
    """EquitiesResearcher uses FRED, RSS, and Polymarket adapters."""
    from src.core.bus.event_bus import EventBus
    from src.pods.base.namespace import PodNamespace
    from src.pods.templates.equities.researcher import EquitiesResearcher

    ns = PodNamespace("equities")
    bus = EventBus()

    fred = FredAdapter(api_key="test")
    rss = RssAdapter()
    mock_snapshot = {"VIXCLS": 15.0, "T10Y2Y": 1.0, "BAMLH0A0HYM2": 3.5}
    news = [
        NewsItem(
            timestamp=datetime.now(timezone.utc),
            source="rss:test",
            headline="AAPL earnings beat expectations",
            body_snippet="Apple reported...",
            entities=["AAPL"],
            dedupe_hash="n1",
        ),
    ]

    with patch.object(fred, "fetch_snapshot", return_value=mock_snapshot), \
         patch.object(rss, "fetch_news", return_value=news):

        researcher = EquitiesResearcher(
            agent_id="equities.researcher",
            pod_id="equities",
            namespace=ns,
            bus=bus,
            fred_adapter=fred,
            rss_adapter=rss,
        )
        result = await researcher.run_cycle({"bar": None})

    assert "universe" in result
    assert ns.get("fred_snapshot") == mock_snapshot
    assert len(ns.get("news_items", [])) == 1


@pytest.mark.asyncio
async def test_equities_researcher_with_mocked_fred():
    """EquitiesResearcher stores FRED snapshot in namespace."""
    from src.core.bus.event_bus import EventBus
    from src.pods.base.namespace import PodNamespace
    from src.pods.templates.equities.researcher import EquitiesResearcher

    ns = PodNamespace("equities")
    bus = EventBus()

    fred = FredAdapter(api_key="test")
    mock_snapshot = {"VIXCLS": 22.0, "BAMLH0A0HYM2": 4.5, "T10Y2Y": -0.2, "DFF": 5.25}

    with patch.object(fred, "fetch_snapshot", return_value=mock_snapshot):
        researcher = EquitiesResearcher(
            agent_id="equities.researcher",
            pod_id="equities",
            namespace=ns,
            bus=bus,
            fred_adapter=fred,
        )
        result = await researcher.run_cycle({"bar": None})

    assert ns.get("fred_snapshot") == mock_snapshot
    assert "universe" in result


@pytest.mark.asyncio
async def test_equities_researcher_blends_fred_and_polymarket():
    """EquitiesResearcher blends FRED snapshot with Polymarket signals."""
    from src.core.bus.event_bus import EventBus
    from src.pods.base.namespace import PodNamespace
    from src.pods.templates.equities.researcher import EquitiesResearcher

    ns = PodNamespace("equities")
    bus = EventBus()

    fred = FredAdapter(api_key="test")
    rss = RssAdapter()
    mock_snapshot = {"VIXCLS": 15.0, "T10Y2Y": 1.0, "BAMLH0A0HYM2": 3.5}

    with patch.object(fred, "fetch_snapshot", return_value=mock_snapshot), \
         patch.object(rss, "fetch_news", return_value=[]):

        researcher = EquitiesResearcher(
            agent_id="equities.researcher",
            pod_id="equities",
            namespace=ns,
            bus=bus,
            fred_adapter=fred,
            rss_adapter=rss,
        )
        result = await researcher.run_cycle({"bar": None})

    assert ns.get("fred_snapshot") is not None
    assert ns.get("fred_snapshot") == mock_snapshot
    assert "poly_signals" in result
