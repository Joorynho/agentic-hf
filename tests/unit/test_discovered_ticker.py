import pytest
from datetime import date
from src.core.models.execution import DiscoveredTicker

def test_discovered_ticker_defaults():
    t = DiscoveredTicker(
        symbol="NBIS",
        theme="AI Infrastructure",
        thesis="Cloud AI infra provider partnering with NVIDIA/MSFT.",
        discovered_date="2026-04-14",
        next_review_date="2026-04-21",
    )
    assert t.symbol == "NBIS"
    assert t.status == "active"
    assert t.invalidation_reason is None
    assert t.source_headlines == []

def test_discovered_ticker_serializes_to_json():
    t = DiscoveredTicker(
        symbol="VRT",
        theme="Data Centers",
        thesis="Power demand surge from AI buildout.",
        discovered_date="2026-04-14",
        next_review_date="2026-04-21",
    )
    d = t.model_dump(mode="json")
    assert d["symbol"] == "VRT"
    assert d["status"] == "active"
    assert isinstance(d["source_headlines"], list)
