from unittest.mock import MagicMock
from src.core.concentration import aggregate_exposure, check_concentration, MAX_SECTOR_PCT

def _mock_summary(nav: float, buckets: list[tuple[str, float]]):
    s = MagicMock()
    s.risk_metrics.nav = nav
    s.exposure_buckets = []
    for asset_class, pct_nav in buckets:
        b = MagicMock()
        b.asset_class = asset_class
        b.notional_pct_nav = pct_nav
        s.exposure_buckets.append(b)
    return s

def test_aggregate_single_pod():
    summaries = {"equities": _mock_summary(100.0, [("equity", 0.80)])}
    exp = aggregate_exposure(summaries)
    assert abs(exp["equity"] - 0.80) < 0.01

def test_aggregate_cross_pod():
    summaries = {
        "equities":   _mock_summary(100.0, [("equity", 0.80)]),
        "commodities":_mock_summary(100.0, [("equity", 0.20), ("commodity", 0.60)]),
    }
    exp = aggregate_exposure(summaries)
    # equity: (80 + 20) / 200 = 0.50
    assert abs(exp["equity"] - 0.50) < 0.01
    # commodity: 60 / 200 = 0.30
    assert abs(exp["commodity"] - 0.30) < 0.01

def test_check_blocks_at_limit():
    exp = {"equity": MAX_SECTOR_PCT}
    allowed, reason = check_concentration("equity", exp)
    assert not allowed
    assert "equity" in reason

def test_check_allows_below_limit():
    exp = {"equity": 0.30}
    allowed, _ = check_concentration("equity", exp)
    assert allowed

def test_check_missing_sector_allowed():
    allowed, _ = check_concentration("crypto", {})
    assert allowed

def test_empty_summaries():
    exp = aggregate_exposure({})
    assert exp == {}

def test_zero_nav_summaries():
    summaries = {"equities": _mock_summary(0.0, [("equity", 0.80)])}
    exp = aggregate_exposure(summaries)
    assert exp == {}
