from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

SERIES_IDS = [
    # --- Rates & Yields ---
    "DFF",              # Fed Funds Rate (daily)
    "DGS2",             # 2-Year Treasury Yield (daily)
    "DGS10",            # 10-Year Treasury Yield (daily)
    "DGS30",            # 30-Year Treasury Yield (daily)
    "T10Y2Y",           # 10Y-2Y spread / yield curve slope (daily)
    "T10Y3M",           # 10Y-3M spread / recession predictor (daily)
    "MORTGAGE30US",     # 30-Year Fixed Mortgage Rate (weekly)
    # --- Inflation ---
    "T5YIE",            # 5-Year Breakeven Inflation Rate (daily)
    "T10YIE",           # 10-Year Breakeven Inflation Rate (daily)
    # --- Volatility & Risk ---
    "VIXCLS",           # CBOE VIX (daily)
    "BAMLH0A0HYM2",    # ICE BofA HY Credit Spread OAS (daily)
    "NFCI",             # Chicago Fed National Financial Conditions Index (weekly)
    # --- Labor ---
    "UNRATE",           # Unemployment Rate (monthly)
    "ICSA",             # Initial Jobless Claims (weekly)
    # --- Growth & Activity ---
    "INDPRO",           # Industrial Production Index (monthly)
    "RSAFS",            # Advance Retail Sales (monthly)
    "UMCSENT",          # UMich Consumer Sentiment (monthly)
    # --- Inflation (Actuals) ---
    "CPIAUCSL",         # CPI All Urban Consumers (monthly)
    "PCEPILFE",         # Core PCE Price Index — Fed's preferred (monthly)
    # --- Commodities & FX ---
    "DCOILWTICO",       # WTI Crude Oil Price (daily)
    "DTWEXBGS",         # Trade-Weighted USD Index Broad (daily)
    # --- Liquidity ---
    "M2SL",             # M2 Money Supply (monthly)
    "WALCL",            # Fed Balance Sheet Total Assets (weekly)
]

CACHE_TTL = timedelta(hours=1)


class FredAdapter:
    """Fetches macro indicators from the FRED API via fredapi.

    Returns a snapshot dict mapping series_id -> latest float value.
    Results are cached in-memory for 1 hour since FRED data updates daily.
    Gracefully returns {} when the API key is missing or any request fails.
    """

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key if api_key is not None else os.getenv("FRED_API_KEY", "")
        self._has_key = bool(self._api_key)
        self._cache: dict[str, float] = {}
        self._cache_ts: datetime | None = None

    async def fetch_snapshot(self) -> dict[str, float]:
        """Return latest value for each tracked FRED series."""
        if not self._has_key:
            logger.info("FRED_API_KEY not set — returning empty snapshot")
            return {}

        if self._cache_ts and (datetime.now(timezone.utc) - self._cache_ts) < CACHE_TTL:
            return dict(self._cache)

        try:
            import asyncio
            snapshot = await asyncio.to_thread(self._fetch_sync)
            self._cache = snapshot
            self._cache_ts = datetime.now(timezone.utc)
            logger.info("[fred] Fetched %d series", len(snapshot))
            return dict(snapshot)
        except Exception as exc:
            logger.info("[fred] Fetch failed (non-critical): %s", exc)
            return dict(self._cache) if self._cache else {}

    def _fetch_sync(self) -> dict[str, float]:
        from fredapi import Fred

        fred = Fred(api_key=self._api_key)
        snapshot: dict[str, float] = {}

        for sid in SERIES_IDS:
            try:
                series = fred.get_series(sid, observation_start="2024-01-01")
                latest = series.dropna().iloc[-1] if not series.dropna().empty else None
                if latest is not None:
                    snapshot[sid] = float(latest)
            except Exception as exc:
                logger.debug("[fred] Failed to fetch %s: %s", sid, exc)

        return snapshot

    @staticmethod
    def extract(snapshot: dict[str, float], key: str, default: float = 0.0) -> float:
        """Convenience accessor with default."""
        return snapshot.get(key, default)
