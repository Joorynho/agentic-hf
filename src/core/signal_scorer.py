"""Signal quality scoring — tracks which signal conditions precede wins vs losses."""
from __future__ import annotations

import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


class SignalScorer:
    """Associates signal conditions at trade entry with outcomes to compute hit rates.

    Tracks categorical signals like VIX level (low/mid/high), yield curve
    state (inverted/flat/normal), and macro outlook. For each signal
    category+value pair, it records how many trades were wins vs losses.
    """

    def __init__(self, pod_id: str):
        self._pod_id = pod_id
        self._signal_outcomes: dict[str, dict[str, dict]] = defaultdict(
            lambda: defaultdict(lambda: {"wins": 0, "losses": 0, "total_pnl": 0.0})
        )

    def record_trade(self, signal_snapshot: dict, realized_pnl: float) -> None:
        """Record a trade outcome against its signal conditions."""
        if not signal_snapshot:
            return
        is_win = realized_pnl > 0
        categorized = self._categorize_signals(signal_snapshot)
        for category, value in categorized.items():
            bucket = self._signal_outcomes[category][value]
            if is_win:
                bucket["wins"] += 1
            else:
                bucket["losses"] += 1
            bucket["total_pnl"] += realized_pnl

    def ingest_closed_trades(self, closed_trades: list[dict]) -> None:
        """Bulk ingest closed trades to build signal quality data."""
        for trade in closed_trades:
            snap = trade.get("signal_snapshot", {})
            pnl = trade.get("realized_pnl", 0)
            if snap:
                self.record_trade(snap, pnl)

    @staticmethod
    def _categorize_signals(snapshot: dict) -> dict[str, str]:
        """Convert numeric signal values to categorical buckets."""
        cats: dict[str, str] = {}

        vix = snapshot.get("vix") or snapshot.get("VIX")
        if vix is not None:
            try:
                vix_val = float(vix)
                if vix_val < 15:
                    cats["vix_level"] = "low (<15)"
                elif vix_val < 25:
                    cats["vix_level"] = "mid (15-25)"
                else:
                    cats["vix_level"] = "high (>25)"
            except (ValueError, TypeError):
                pass

        yc = snapshot.get("yield_curve") or snapshot.get("T10Y2Y")
        if yc is not None:
            try:
                yc_val = float(yc)
                if yc_val < -0.1:
                    cats["yield_curve"] = "inverted"
                elif yc_val < 0.5:
                    cats["yield_curve"] = "flat"
                else:
                    cats["yield_curve"] = "normal"
            except (ValueError, TypeError):
                pass

        outlook = snapshot.get("macro_outlook")
        if outlook and isinstance(outlook, str):
            cats["macro_outlook"] = outlook.lower()

        strategy = snapshot.get("strategy_tag")
        if strategy and isinstance(strategy, str):
            cats["strategy"] = strategy

        return cats

    def get_hit_rates(self) -> dict[str, dict[str, dict]]:
        """Get hit rates for all signal categories."""
        results: dict[str, dict[str, dict]] = {}
        for category, values in self._signal_outcomes.items():
            results[category] = {}
            for value, stats in values.items():
                total = stats["wins"] + stats["losses"]
                results[category][value] = {
                    "hit_rate": stats["wins"] / total if total > 0 else 0.0,
                    "trades": total,
                    "wins": stats["wins"],
                    "losses": stats["losses"],
                    "avg_pnl": stats["total_pnl"] / total if total > 0 else 0.0,
                }
        return results

    def format_for_prompt(self) -> str:
        """Format signal quality data for PM prompt injection."""
        hit_rates = self.get_hit_rates()
        if not hit_rates:
            return ""

        lines = ["Signal quality (win rates by condition):"]
        for category, values in hit_rates.items():
            for value, stats in values.items():
                if stats["trades"] >= 2:
                    lines.append(
                        f"  {category}={value}: "
                        f"{stats['hit_rate']:.0%} hit rate "
                        f"({stats['trades']} trades, avg ${stats['avg_pnl']:.0f})"
                    )
        return "\n".join(lines) if len(lines) > 1 else ""

    def to_state_dict(self) -> dict:
        """Serialize for persistence."""
        return {
            "pod_id": self._pod_id,
            "signal_outcomes": {
                cat: dict(vals)
                for cat, vals in self._signal_outcomes.items()
            },
        }

    @classmethod
    def load_from_state(cls, state: dict) -> SignalScorer:
        """Restore from persisted state."""
        scorer = cls(pod_id=state.get("pod_id", "unknown"))
        raw = state.get("signal_outcomes", {})
        for cat, vals in raw.items():
            for val, stats in vals.items():
                scorer._signal_outcomes[cat][val] = dict(stats)
        return scorer
