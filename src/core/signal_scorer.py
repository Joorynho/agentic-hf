"""Signal quality scoring — tracks which signal conditions precede wins vs losses."""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime

logger = logging.getLogger(__name__)

_AGE_BUCKETS = [(0, 1, "0-1d"), (1, 3, "1-3d"), (3, 7, "3-7d"), (7, 999, "7d+")]


class SignalScorer:
    """Associates signal conditions at trade entry with outcomes to compute hit rates.

    Tracks categorical signals like VIX level (low/mid/high), yield curve
    state (inverted/flat/normal), and macro outlook. For each signal
    category+value pair, it records how many trades were wins vs losses.
    Also tracks signal-to-outcome time for decay analysis.
    """

    def __init__(self, pod_id: str):
        self._pod_id = pod_id
        self._signal_outcomes: dict[str, dict[str, dict]] = defaultdict(
            lambda: defaultdict(lambda: {"wins": 0, "losses": 0, "total_pnl": 0.0})
        )
        self._trade_timings: list[dict] = []
        self._ingested_ids: set[str] = set()

    def record_trade(self, signal_snapshot: dict, realized_pnl: float,
                     entry_time: str = "", exit_time: str = "") -> None:
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

        days = self._compute_days(entry_time, exit_time)
        if days is not None:
            self._trade_timings.append({
                "days": days,
                "is_win": is_win,
                "pnl": realized_pnl,
            })

    @staticmethod
    def _compute_days(entry_time: str, exit_time: str) -> float | None:
        if not entry_time or not exit_time:
            return None
        try:
            et = datetime.fromisoformat(entry_time)
            xt = datetime.fromisoformat(exit_time)
            return max(0, (xt - et).total_seconds() / 86400)
        except (ValueError, TypeError):
            return None

    def ingest_closed_trades(self, closed_trades: list[dict]) -> None:
        """Bulk ingest closed trades to build signal quality data."""
        for trade in closed_trades:
            sym = trade.get("symbol", "")
            entry_t = trade.get("entry_time", "")
            exit_t = trade.get("exit_time", "")
            pnl = trade.get("realized_pnl", 0)
            trade_key = f"{sym}-{entry_t}-{exit_t}-{pnl}"
            if trade_key in self._ingested_ids:
                continue
            self._ingested_ids.add(trade_key)
            snap = trade.get("signal_snapshot", {})
            if snap:
                self.record_trade(snap, pnl, entry_time=entry_t, exit_time=exit_t)

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

    def get_decay_analysis(self) -> dict:
        """Win rate by signal age bucket and average time-to-outcome."""
        if len(self._trade_timings) < 2:
            return {}
        result: dict = {}
        for lo, hi, label in _AGE_BUCKETS:
            trades_in_bucket = [t for t in self._trade_timings if lo <= t["days"] < hi]
            if not trades_in_bucket:
                continue
            wins = sum(1 for t in trades_in_bucket if t["is_win"])
            total = len(trades_in_bucket)
            avg_days = sum(t["days"] for t in trades_in_bucket) / total
            result[label] = {
                "win_rate": wins / total if total > 0 else 0.0,
                "trades": total,
                "avg_days": round(avg_days, 1),
            }

        winners = [t for t in self._trade_timings if t["is_win"]]
        losers = [t for t in self._trade_timings if not t["is_win"]]
        result["_summary"] = {
            "avg_winner_days": round(sum(t["days"] for t in winners) / len(winners), 1) if winners else 0,
            "avg_loser_days": round(sum(t["days"] for t in losers) / len(losers), 1) if losers else 0,
        }
        return result

    def format_for_prompt(self) -> str:
        """Format signal quality data for PM prompt injection."""
        hit_rates = self.get_hit_rates()
        lines = []
        if hit_rates:
            hit_lines = []
            for category, values in hit_rates.items():
                for value, stats in values.items():
                    if stats["trades"] >= 2:
                        hit_lines.append(
                            f"  {category}={value}: "
                            f"{stats['hit_rate']:.0%} hit rate "
                            f"({stats['trades']} trades, avg ${stats['avg_pnl']:.0f})"
                        )
            if hit_lines:
                lines.append("Signal quality (win rates by condition):")
                lines.extend(hit_lines)

        decay = self.get_decay_analysis()
        if decay:
            lines.append("Signal timing (win rate by age):")
            for label in ["0-1d", "1-3d", "3-7d", "7d+"]:
                if label in decay:
                    d = decay[label]
                    lines.append(f"  Signals acted on within {label}: {d['win_rate']:.0%} win rate ({d['trades']} trades)")
            summary = decay.get("_summary", {})
            if summary.get("avg_winner_days"):
                lines.append(f"  Avg time to outcome: winners={summary['avg_winner_days']:.1f}d, losers={summary['avg_loser_days']:.1f}d")

        return "\n".join(lines) if lines else ""

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
