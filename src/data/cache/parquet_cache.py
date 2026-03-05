from __future__ import annotations

import os
from datetime import date

import pandas as pd

from src.core.models.market import Bar


class ParquetCache:
    def __init__(self, cache_dir: str):
        self._dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    def _path(self, symbol: str) -> str:
        return os.path.join(self._dir, f"{symbol}.parquet")

    def get(self, symbol: str, start: date, end: date) -> list[Bar] | None:
        path = self._path(symbol)
        if not os.path.exists(path):
            return None
        df = pd.read_parquet(path)
        mask = (df.index >= pd.Timestamp(start)) & (df.index <= pd.Timestamp(end))
        subset = df[mask]
        if subset.empty:
            return None
        return self._df_to_bars(symbol, subset)

    def save(self, symbol: str, bars: list[Bar]) -> None:
        if not bars:
            return
        records = [b.model_dump() for b in bars]
        df = pd.DataFrame(records).set_index("timestamp")
        path = self._path(symbol)
        if os.path.exists(path):
            existing = pd.read_parquet(path)
            df = pd.concat([existing, df]).drop_duplicates()
        df.to_parquet(path)

    def completeness_score(self, symbol: str, start: date, end: date) -> float:
        bars = self.get(symbol, start, end)
        if bars is None:
            return 0.0
        expected_days = len(pd.bdate_range(start, end))
        return min(1.0, len(bars) / max(1, expected_days))

    def _df_to_bars(self, symbol: str, df: pd.DataFrame) -> list[Bar]:
        bars = []
        for ts, row in df.iterrows():
            bars.append(Bar(
                symbol=symbol,
                timestamp=ts.to_pydatetime().replace(tzinfo=None) if hasattr(ts, 'to_pydatetime') else ts,
                open=float(row.get("open", 0)),
                high=float(row.get("high", 0)),
                low=float(row.get("low", 0)),
                close=float(row.get("close", 0)),
                volume=float(row.get("volume", 0)),
                adj_close=float(row["adj_close"]) if pd.notna(row.get("adj_close")) else None,
                source=str(row.get("source", "cache")),
            ))
        return bars
