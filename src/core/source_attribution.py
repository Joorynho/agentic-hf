"""Track per-source win rates and compute dynamic macro score weights."""
from __future__ import annotations

MIN_WEIGHT = 0.15
SOURCES    = ("fred", "poly", "news")


def compute_dynamic_weights(win_rates: dict[str, float]) -> dict[str, float]:
    """
    win_rates: {"fred": 0.65, "poly": 0.38, "news": 0.55}
    Returns weights summing to 1.0, each >= MIN_WEIGHT.

    Uses an iterative clamp-and-redistribute approach so that floored sources
    never drop below MIN_WEIGHT after re-normalisation.
    """
    raw = {s: max(0.01, win_rates.get(s, 0.5)) for s in SOURCES}
    total = sum(raw.values())
    weights = {s: v / total for s, v in raw.items()}

    # Iteratively clamp sources at the floor and redistribute the surplus to
    # the unclamped sources, repeating until convergence (max 10 passes).
    for _ in range(10):
        clamped = {s for s, v in weights.items() if v < MIN_WEIGHT}
        if not clamped:
            break
        # Lock clamped sources at floor; pool leftover weight for the rest
        allocated = MIN_WEIGHT * len(clamped)
        remaining = 1.0 - allocated
        free = {s: weights[s] for s in weights if s not in clamped}
        free_total = sum(free.values())
        if free_total <= 0:
            # Edge case: all sources are below the floor — distribute equally
            weights = {s: round(1.0 / len(SOURCES), 4) for s in SOURCES}
            break
        new_weights: dict[str, float] = {}
        for s in SOURCES:
            if s in clamped:
                new_weights[s] = MIN_WEIGHT
            else:
                new_weights[s] = free[s] / free_total * remaining
        weights = new_weights

    # Final rounding pass — ensure exact sum of 1.0
    rounded = {s: round(v, 4) for s, v in weights.items()}
    # Correct any floating-point drift on the largest weight
    diff = round(1.0 - sum(rounded.values()), 4)
    if diff != 0:
        largest = max(rounded, key=lambda s: rounded[s])
        rounded[largest] = round(rounded[largest] + diff, 4)
    return rounded


class SourceAttributor:
    """Ingest closed trades and derive per-source win rates from signal_snapshot."""

    def __init__(self) -> None:
        self._counts: dict[str, dict[str, int]] = {s: {"wins": 0, "total": 0} for s in SOURCES}

    def ingest_closed_trade(self, trade: dict) -> None:
        """
        trade must have:
          - signal_snapshot: dict (may contain fred_score, poly_score, news_score / social_score keys)
          - realized_pnl: float (positive = win)
        """
        snapshot = trade.get("signal_snapshot") or {}
        is_win   = (trade.get("realized_pnl") or 0.0) > 0

        source_key_map = {
            "fred": ("fred_score", "fred"),
            "poly": ("poly_score", "poly_sentiment"),
            "news": ("news_score", "social_score", "news"),
        }
        for source, keys in source_key_map.items():
            score = None
            for k in keys:
                if k in snapshot:
                    score = snapshot[k]
                    break
            if score is not None:
                self._counts[source]["total"] += 1
                if is_win:
                    self._counts[source]["wins"] += 1

    def ingest_batch(self, trades: list[dict]) -> None:
        for trade in trades:
            self.ingest_closed_trade(trade)

    def win_rates(self) -> dict[str, float]:
        result = {}
        for s in SOURCES:
            total = self._counts[s]["total"]
            result[s] = self._counts[s]["wins"] / total if total > 0 else 0.5
        return result

    def weights(self) -> dict[str, float]:
        return compute_dynamic_weights(self.win_rates())

    def sample_counts(self) -> dict[str, int]:
        return {s: self._counts[s]["total"] for s in SOURCES}

    def summary(self) -> str:
        rates  = self.win_rates()
        wts    = self.weights()
        counts = self.sample_counts()
        lines  = ["SOURCE ATTRIBUTION (win rates → dynamic weights):"]
        for s in SOURCES:
            lines.append(
                f"  {s:<5}  win={rates[s]:.0%}  n={counts[s]}  weight={wts[s]:.0%}"
            )
        return "\n".join(lines)
