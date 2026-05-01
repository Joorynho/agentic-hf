"""Benchmark reference returns per pod (yfinance daily closes)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class BenchmarkAdapter:
    """Maps each pod to a liquid ETF/index proxy; fetches return since session start."""

    BENCHMARKS = {
        "equities": "SPY",
        "commodities": "GLD",
        "crypto": "BTC-USD",
        "fx": "UUP",
    }

    def __init__(self) -> None:
        self._start_prices: dict[str, float] = {}

    async def fetch_all(self, since_date: str) -> dict:
        """Return ``{pod_id: {symbol, start_price, current_price, return_pct}}``.

        On any failure returns ``{}`` (non-fatal).
        """
        try:
            import yfinance as yf
        except Exception as e:
            logger.debug("[benchmark] yfinance unavailable: %s", e)
            return {}

        out: dict = {}
        try:
            since_dt = datetime.strptime(since_date[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            since_dt = datetime.now(timezone.utc)

        for pod_id, symbol in self.BENCHMARKS.items():
            try:
                t = yf.Ticker(symbol)
                hist = t.history(start=since_dt.date().isoformat(), interval="1d")
                if hist is None or hist.empty:
                    continue
                start_p = float(hist["Close"].iloc[0])
                cur_p = float(hist["Close"].iloc[-1])
                cache_key = f"{pod_id}:{symbol}"
                if cache_key not in self._start_prices:
                    self._start_prices[cache_key] = start_p
                base = self._start_prices.get(cache_key, start_p)
                ret_pct = (cur_p - base) / base if base else 0.0
                out[pod_id] = {
                    "symbol": symbol,
                    "start_price": round(base, 4),
                    "current_price": round(cur_p, 4),
                    "return_pct": round(ret_pct * 100, 2),
                }
            except Exception as e:
                logger.debug("[benchmark] %s %s: %s", pod_id, symbol, e)
        return out
