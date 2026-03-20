"""Detect positions that have exceeded their max_hold_days and emit aging alerts."""
from __future__ import annotations
from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.backtest.accounting.portfolio import PortfolioAccountant

DEFAULT_MAX_HOLD = 30   # days, fallback when not set per-position


def _get_open_symbols(accountant: "PortfolioAccountant") -> list[str]:
    """Return open position symbols from the accountant.

    Supports both the real PortfolioAccountant (uses ._positions) and
    test mocks that expose a .positions property returning a plain dict.
    """
    # Try ._positions first (real PortfolioAccountant internal dict)
    raw = getattr(accountant, "_positions", None)
    if isinstance(raw, dict):
        return list(raw.keys())

    # Fallback: .positions property (used in unit tests via PropertyMock)
    via_prop = getattr(accountant, "positions", None)
    if isinstance(via_prop, dict):
        return list(via_prop.keys())

    return []


def check_aging(accountant: "PortfolioAccountant") -> list[dict]:
    """
    Scan all open positions for max_hold_days violations.
    Returns list of dicts: {symbol, pod_id, days_held, max_hold_days, entry_date}
    """
    alerts = []
    today = date.today()

    for symbol in _get_open_symbols(accountant):
        meta = accountant._entry_metadata.get(symbol, {})
        max_hold = int(meta.get("max_hold_days") or DEFAULT_MAX_HOLD)
        entry_str = accountant._entry_dates.get(symbol, "")
        if not entry_str:
            continue
        try:
            entry = date.fromisoformat(entry_str)
        except ValueError:
            continue
        days_held = (today - entry).days
        if days_held >= max_hold:
            alerts.append({
                "symbol": symbol,
                "pod_id": accountant._pod_id,
                "days_held": days_held,
                "max_hold_days": max_hold,
                "entry_date": entry_str,
            })
    return alerts
