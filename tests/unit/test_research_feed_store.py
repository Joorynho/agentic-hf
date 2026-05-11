from datetime import datetime, timezone

from src.core.research_feed import ResearchFeedStore, classify_research_item


def test_classify_research_item_routes_macro_asset_factors_and_tickers():
    item = {
        "title": "Hormuz oil shock lifts gold as real yields fall",
        "text": "WTI crude, gold, GLD, and USO rally while the dollar weakens.",
        "category": "Commodities",
        "sentiment": 0.4,
    }

    routing = classify_research_item(item)

    assert "commodities" in routing["asset_classes"]
    assert {"energy", "metals", "geopolitics", "real_yields", "usd"}.intersection(routing["factors"])
    assert {"GLD", "USO"}.issubset(set(routing["tickers"]))
    assert routing["urgency"] > 0.5


def test_research_feed_store_dedupes_items_and_records_source_health(tmp_path):
    db_path = tmp_path / "research_feed.duckdb"
    store = ResearchFeedStore(str(db_path))
    try:
        item = {
            "title": "Bitcoin and Ethereum ETF flows improve",
            "text": "BTC and ETH liquidity improves as ETF flows recover.",
            "url": "https://example.com/crypto-etf-flows",
            "username": "Crypto Regulation",
            "category": "Crypto",
            "timestamp": "2026-05-08T10:00:00+00:00",
            "sentiment": 0.25,
        }

        assert store.record_items([item], "news", ts=datetime(2026, 5, 8, 10, 1, tzinfo=timezone.utc)) == 1
        assert store.record_items([item], "news", ts=datetime(2026, 5, 8, 10, 2, tzinfo=timezone.utc)) == 1

        summary = store.summary()
        assert summary["item_count"] == 1
        persisted = summary["items"][0]
        assert persisted["source"] == "Crypto Regulation"
        assert "crypto" in persisted["asset_classes"]
        assert {"BTC/USD", "ETH/USD"}.issubset(set(persisted["tickers"]))

        sources = {row["source"]: row for row in summary["sources"]}
        assert sources["Crypto Regulation"]["status"] == "ok"
        assert sources["Crypto Regulation"]["item_count"] == 1
    finally:
        store.close()


def test_research_feed_source_failures_increment_and_success_resets(tmp_path):
    db_path = tmp_path / "research_feed.duckdb"
    store = ResearchFeedStore(str(db_path))
    try:
        store.record_source_status("Reuters Markets", "news", "error", error="timeout")
        store.record_source_status("Reuters Markets", "news", "error", error="timeout")
        failed = store.get_source_health()[0]
        assert failed["status"] == "error"
        assert failed["consecutive_failures"] == 2

        store.record_source_status("Reuters Markets", "news", "ok", item_count=3)
        recovered = store.get_source_health()[0]
        assert recovered["status"] == "ok"
        assert recovered["consecutive_failures"] == 0
        assert recovered["item_count"] == 3
    finally:
        store.close()
