import pytest
from unittest.mock import AsyncMock, MagicMock
from src.pods.templates.equities.researcher import EquitiesResearcher
from src.core.config.universes import EQUITIES_SEED


@pytest.fixture
def researcher():
    r = EquitiesResearcher.__new__(EquitiesResearcher)
    store = {}
    r._ns = MagicMock()
    r._ns.get = lambda k, d=None: store.get(k, d)
    r._ns.set = lambda k, v: store.update({k: v})
    r._pod_id = "equities"
    r._web_searcher = MagicMock()
    r._web_searcher.search = AsyncMock(return_value=[])
    r._web_searcher.fetch_page = AsyncMock(return_value="")
    r._last_theme_scan_date = None
    return r


def test_should_run_theme_scan_first_time(researcher):
    assert researcher._should_run_theme_scan() is True


def test_should_not_run_theme_scan_same_day(researcher):
    from datetime import date
    researcher._last_theme_scan_date = date.today().isoformat()
    assert researcher._should_run_theme_scan() is False


def test_load_discovered_universe_empty(researcher):
    result = researcher._load_discovered_universe()
    assert result == {}


def test_build_active_universe_merges_seed_and_discovered(researcher):
    discovered = {
        "NBIS": {"symbol": "NBIS", "status": "active"},
        "VRT": {"symbol": "VRT", "status": "inactive"},
    }
    universe = researcher._build_active_universe(discovered)
    assert "NBIS" in universe
    assert "VRT" not in universe
    for sym in EQUITIES_SEED:
        assert sym in universe
