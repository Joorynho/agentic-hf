"""Events calendar adapter — earnings dates (yfinance) + FOMC schedule."""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import date, datetime, timedelta

logger = logging.getLogger(__name__)

_CACHE_TTL = 86400  # 24 hours

FOMC_2026 = [
    date(2026, 1, 28),
    date(2026, 3, 18),
    date(2026, 5, 6),
    date(2026, 6, 17),
    date(2026, 7, 29),
    date(2026, 9, 16),
    date(2026, 11, 4),
    date(2026, 12, 16),
]


class EventsCalendarAdapter:
    """Fetches earnings dates and FOMC meetings for upcoming-event warnings."""

    def __init__(self):
        self._earnings_cache: dict[str, tuple[float, list[dict]]] = {}

    async def fetch_earnings(self, symbols: list[str]) -> list[dict]:
        """Get upcoming earnings dates from yfinance."""
        now = time.time()
        cached = self._earnings_cache.get("_all")
        if cached and now - cached[0] < _CACHE_TTL:
            return [e for e in cached[1] if e["symbol"] in symbols]

        try:
            results = await asyncio.get_event_loop().run_in_executor(
                None, self._sync_fetch_earnings, symbols
            )
            self._earnings_cache["_all"] = (now, results)
            return results
        except Exception as e:
            logger.warning("[events_calendar] Earnings fetch failed: %s", e)
            return []

    @staticmethod
    def _sync_fetch_earnings(symbols: list[str]) -> list[dict]:
        import yfinance as yf
        today = date.today()
        results: list[dict] = []
        for sym in symbols[:30]:
            try:
                ticker = yf.Ticker(sym)
                cal = ticker.calendar
                if cal is None or (isinstance(cal, dict) and not cal):
                    continue
                if isinstance(cal, dict):
                    earnings_date = cal.get("Earnings Date")
                    if isinstance(earnings_date, list) and earnings_date:
                        earnings_date = earnings_date[0]
                    if earnings_date:
                        if hasattr(earnings_date, "date"):
                            ed = earnings_date.date()
                        else:
                            ed = earnings_date
                        days_until = (ed - today).days
                        if 0 <= days_until <= 30:
                            results.append({
                                "symbol": sym,
                                "event_type": "earnings",
                                "date": str(ed),
                                "days_until": days_until,
                            })
            except Exception:
                continue
        return results

    async def fetch_fomc_dates(self) -> list[dict]:
        """Return upcoming FOMC meeting dates."""
        today = date.today()
        results: list[dict] = []
        for d in FOMC_2026:
            days_until = (d - today).days
            if 0 <= days_until <= 30:
                results.append({
                    "symbol": "FOMC",
                    "event_type": "FOMC",
                    "date": str(d),
                    "days_until": days_until,
                })
        return results

    async def fetch_upcoming_events(self, symbols: list[str]) -> list[dict]:
        """Merge earnings + FOMC, sorted by date, filtered to next 14 days."""
        earnings = await self.fetch_earnings(symbols)
        fomc = await self.fetch_fomc_dates()
        all_events = earnings + fomc
        all_events = [e for e in all_events if e.get("days_until", 99) <= 14]
        all_events.sort(key=lambda e: e.get("days_until", 99))
        return all_events
