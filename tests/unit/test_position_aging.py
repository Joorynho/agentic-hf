from datetime import date, timedelta
from unittest.mock import MagicMock, PropertyMock
from src.core.position_aging import check_aging, DEFAULT_MAX_HOLD


def _make_accountant(positions_dict, entry_dates, entry_metadata):
    acc = MagicMock()
    acc._pod_id = "equities"
    type(acc).positions = PropertyMock(return_value=positions_dict)
    acc._entry_dates = entry_dates
    acc._entry_metadata = entry_metadata
    # Ensure _positions is not a plain dict so the fallback path is exercised
    acc._positions = MagicMock()  # not a dict — triggers fallback to .positions
    return acc


def test_overdue_position_flagged():
    old_date = (date.today() - timedelta(days=35)).isoformat()
    acc = _make_accountant(
        {"AAPL": MagicMock()},
        {"AAPL": old_date},
        {"AAPL": {"max_hold_days": 30}},
    )
    alerts = check_aging(acc)
    assert len(alerts) == 1
    assert alerts[0]["symbol"] == "AAPL"
    assert alerts[0]["days_held"] >= 30


def test_fresh_position_not_flagged():
    today = date.today().isoformat()
    acc = _make_accountant(
        {"AAPL": MagicMock()},
        {"AAPL": today},
        {"AAPL": {"max_hold_days": 30}},
    )
    alerts = check_aging(acc)
    assert alerts == []


def test_default_max_hold_used_when_missing():
    old_date = (date.today() - timedelta(days=DEFAULT_MAX_HOLD + 5)).isoformat()
    acc = _make_accountant(
        {"MSFT": MagicMock()},
        {"MSFT": old_date},
        {"MSFT": {}},  # no max_hold_days
    )
    alerts = check_aging(acc)
    assert len(alerts) == 1


def test_missing_entry_date_skipped():
    acc = _make_accountant(
        {"AAPL": MagicMock()},
        {},   # no entry date
        {"AAPL": {"max_hold_days": 30}},
    )
    alerts = check_aging(acc)
    assert alerts == []


def test_multiple_positions_mixed():
    today = date.today().isoformat()
    old = (date.today() - timedelta(days=40)).isoformat()
    acc = _make_accountant(
        {"AAPL": MagicMock(), "MSFT": MagicMock()},
        {"AAPL": today, "MSFT": old},
        {"AAPL": {"max_hold_days": 30}, "MSFT": {"max_hold_days": 30}},
    )
    alerts = check_aging(acc)
    syms = [a["symbol"] for a in alerts]
    assert "MSFT" in syms
    assert "AAPL" not in syms
