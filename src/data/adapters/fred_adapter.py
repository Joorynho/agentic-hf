from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

SERIES_IDS = [
    # --- US Rates & Yields ---
    "DFF",              # Fed Funds Rate (daily)
    "FEDFUNDS",         # Fed Funds Rate (monthly avg)
    "DGS2",             # 2-Year Treasury Yield (daily)
    "DGS10",            # 10-Year Treasury Yield (daily)
    "DGS30",            # 30-Year Treasury Yield (daily)
    "T10Y2Y",           # 10Y-2Y spread / yield curve slope (daily)
    "T10Y3M",           # 10Y-3M spread / recession predictor (daily)
    "MORTGAGE30US",     # 30-Year Fixed Mortgage Rate (weekly)
    # --- International Central Bank Rates ---
    "ECBMRRFR",         # ECB Main Refinancing Rate (monthly)
    "ECBDFR",           # ECB Deposit Facility Rate (monthly)
    "IRSTCI01GBM156N",  # UK Interbank Rate — proxy for BOE policy rate (monthly, OECD)
    "IRSTCB01JPM156N",  # Bank of Japan Central Bank Rate (monthly, OECD)
    "IRSTCI01AUM156N",  # Australia Interbank Rate — proxy for RBA cash rate (monthly, OECD)
    "IRSTCB01CAM156N",  # Bank of Canada Central Bank Rate (monthly, OECD)
    "IRSTCI01CHM156N",  # Swiss National Bank Interbank Rate (monthly, OECD)
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

GLOBAL_RATE_MAP: dict[str, tuple[str, str]] = {
    "FEDFUNDS":         ("US Fed",       "Fed Funds Rate"),
    "DFF":              ("US Fed",       "Fed Funds Effective (daily)"),
    "ECBMRRFR":         ("ECB",          "Main Refinancing Rate"),
    "ECBDFR":           ("ECB",          "Deposit Facility Rate"),
    "IRSTCI01GBM156N":  ("Bank of England", "Interbank Rate"),
    "IRSTCB01JPM156N":  ("Bank of Japan",   "Central Bank Rate"),
    "IRSTCI01AUM156N":  ("RBA (Australia)", "Interbank Rate"),
    "IRSTCB01CAM156N":  ("Bank of Canada",  "Central Bank Rate"),
    "IRSTCI01CHM156N":  ("SNB (Switzerland)", "Interbank Rate"),
}

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
                start = "2020-01-01" if sid in GLOBAL_RATE_MAP else "2024-01-01"
                series = fred.get_series(sid, observation_start=start)
                latest = series.dropna().iloc[-1] if not series.dropna().empty else None
                if latest is not None:
                    snapshot[sid] = float(latest)
                else:
                    logger.info("[fred] Series %s returned no data (start=%s)", sid, start)
            except Exception as exc:
                logger.info("[fred] Failed to fetch %s: %s", sid, exc)

        return snapshot

    @staticmethod
    def extract(snapshot: dict[str, float], key: str, default: float = 0.0) -> float:
        """Convenience accessor with default."""
        return snapshot.get(key, default)

    @staticmethod
    def build_global_rate_table(snapshot: dict[str, float]) -> dict[str, dict]:
        """Build a structured global rate table from the snapshot.

        Returns a dict of central bank -> {rate_name, value} entries.
        Only includes series that were successfully fetched.
        """
        table: dict[str, dict] = {}
        for series_id, (bank, rate_name) in GLOBAL_RATE_MAP.items():
            val = snapshot.get(series_id)
            if val is not None:
                table[bank] = {"rate_name": rate_name, "value": round(val, 3)}
        return table

    @staticmethod
    def format_rate_table_text(snapshot: dict[str, float]) -> str:
        """Format a human-readable global rate table for LLM prompt injection."""
        table = FredAdapter.build_global_rate_table(snapshot)
        if not table:
            return "Global central bank rates: unavailable"
        lines = ["Global Central Bank Policy Rates:"]
        for bank, info in table.items():
            lines.append(f"  {bank}: {info['value']:.2f}% ({info['rate_name']})")
        return "\n".join(lines)
