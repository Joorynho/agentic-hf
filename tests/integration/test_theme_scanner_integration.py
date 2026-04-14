"""Integration test: ThemeScanner -> EquitiesResearcher -> universe expansion."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.data.services.theme_scanner import ThemeScanner
from src.core.models.execution import DiscoveredTicker
from src.core.config.universes import EQUITIES_SEED


@pytest.mark.asyncio
async def test_scanner_adds_tickers_not_in_seed():
    """Discovered tickers should be new symbols not already in seed universe."""
    ws = MagicMock()
    ws.search = AsyncMock(return_value=[
        {"title": "AI stocks surge", "snippet": "AI infra boom.", "url": "https://ex.com"}
    ])
    ws.fetch_page = AsyncMock(return_value="AI infrastructure spending hits record highs.")

    scanner = ThemeScanner(web_searcher=ws)

    with patch("src.data.services.theme_scanner.llm_chat") as mock_llm, \
         patch("src.data.services.theme_scanner.has_llm_key", return_value=True):
        mock_llm.side_effect = [
            '{"themes": [{"name": "AI Infra", "thesis": "Capex surge.", "confidence": 0.9, "tickers": [{"symbol": "NBIS", "reason": "NVIDIA partner"}]}]}',
            '{"valid": true, "reason": "US-listed"}',
        ]
        new_tickers = await scanner.scan(
            headlines=[{"title": "AI boom", "sentiment": 0.9}],
            poly_signals=[],
            fred_snapshot={"VIXCLS": 18.0, "DGS10": 4.2},
            existing_discovered={},
            existing_universe=list(EQUITIES_SEED),
            month="April",
            year="2026",
        )

    assert len(new_tickers) == 1
    assert new_tickers[0].symbol == "NBIS"
    assert new_tickers[0].symbol not in EQUITIES_SEED
    assert new_tickers[0].status == "active"
    assert new_tickers[0].thesis != ""


@pytest.mark.asyncio
async def test_scanner_skips_seed_symbols():
    """Scanner should never add a symbol already in EQUITIES_SEED."""
    ws = MagicMock()
    ws.search = AsyncMock(return_value=[])
    ws.fetch_page = AsyncMock(return_value="")
    scanner = ThemeScanner(web_searcher=ws)

    with patch("src.data.services.theme_scanner.llm_chat") as mock_llm, \
         patch("src.data.services.theme_scanner.has_llm_key", return_value=True):
        mock_llm.side_effect = [
            '{"themes": [{"name": "AI", "thesis": "GPU demand.", "confidence": 0.9, "tickers": [{"symbol": "NVDA", "reason": "Market leader"}]}]}',
        ]
        new_tickers = await scanner.scan(
            headlines=[],
            poly_signals=[],
            fred_snapshot={},
            existing_discovered={},
            existing_universe=list(EQUITIES_SEED),
            month="April",
            year="2026",
        )

    assert len(new_tickers) == 0  # NVDA already in seed


@pytest.mark.asyncio
async def test_build_active_universe_always_contains_full_seed():
    """Active universe must always include every seed symbol."""
    from src.pods.templates.equities.researcher import EquitiesResearcher
    r = EquitiesResearcher.__new__(EquitiesResearcher)
    r._ns = MagicMock()
    r._pod_id = "equities"
    r._last_theme_scan_date = None

    discovered = {
        "NBIS": {"symbol": "NBIS", "status": "active"},
        "FAKEXYZ": {"symbol": "FAKEXYZ", "status": "inactive"},
    }
    universe = r._build_active_universe(discovered)

    for sym in EQUITIES_SEED:
        assert sym in universe, f"Seed symbol {sym} missing from universe"
    assert "NBIS" in universe
    assert "FAKEXYZ" not in universe


@pytest.mark.asyncio
async def test_thesis_review_inactive_ticker_removed_from_universe():
    """Ticker marked inactive should not appear in active universe."""
    from src.pods.templates.equities.researcher import EquitiesResearcher
    r = EquitiesResearcher.__new__(EquitiesResearcher)
    r._ns = MagicMock()
    r._pod_id = "equities"
    r._last_theme_scan_date = None

    discovered = {
        "NBIS": {"symbol": "NBIS", "status": "inactive", "invalidation_reason": "Partnership ended"},
    }
    universe = r._build_active_universe(discovered)
    assert "NBIS" not in universe


def test_discovered_ticker_persistence_round_trip():
    """DiscoveredTicker can be serialized and deserialized for memory.json storage."""
    original = DiscoveredTicker(
        symbol="NBIS",
        theme="AI Infrastructure",
        thesis="NVIDIA/MSFT cloud partnership driving revenue.",
        discovered_date="2026-04-14",
        next_review_date="2026-04-21",
        status="active",
        source_headlines=["Nebius partners with NVIDIA"],
    )
    serialized = original.model_dump(mode="json")
    restored = DiscoveredTicker(**serialized)

    assert restored.symbol == original.symbol
    assert restored.theme == original.theme
    assert restored.thesis == original.thesis
    assert restored.status == original.status
    assert restored.source_headlines == original.source_headlines
