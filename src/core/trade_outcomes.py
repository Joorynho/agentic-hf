"""Aggregates closed-trade outcomes and formats them as context for PM prompts."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class TradeOutcomeTracker:
    """Tracks closed trades and computes aggregate statistics for PM feedback."""

    def __init__(self, pod_id: str):
        self._pod_id = pod_id
        self._trades: list[dict] = []

    def ingest(self, closed_trades: list[dict]) -> None:
        """Ingest new closed trades (deduplicates by checking length delta)."""
        if len(closed_trades) > len(self._trades):
            self._trades = list(closed_trades)

    @property
    def total_trades(self) -> int:
        return len(self._trades)

    @property
    def win_rate(self) -> float:
        if not self._trades:
            return 0.0
        wins = sum(1 for t in self._trades if t.get("realized_pnl", 0) > 0)
        return wins / len(self._trades)

    @property
    def avg_pnl(self) -> float:
        if not self._trades:
            return 0.0
        return sum(t.get("realized_pnl", 0) for t in self._trades) / len(self._trades)

    @property
    def total_pnl(self) -> float:
        return sum(t.get("realized_pnl", 0) for t in self._trades)

    @property
    def avg_winner(self) -> float:
        winners = [t["realized_pnl"] for t in self._trades if t.get("realized_pnl", 0) > 0]
        return sum(winners) / len(winners) if winners else 0.0

    @property
    def avg_loser(self) -> float:
        losers = [t["realized_pnl"] for t in self._trades if t.get("realized_pnl", 0) < 0]
        return sum(losers) / len(losers) if losers else 0.0

    def per_symbol_stats(self) -> dict[str, dict]:
        """Per-symbol trade statistics."""
        stats: dict[str, dict] = {}
        for t in self._trades:
            sym = t.get("symbol", "?")
            if sym not in stats:
                stats[sym] = {"trades": 0, "wins": 0, "total_pnl": 0.0}
            stats[sym]["trades"] += 1
            stats[sym]["total_pnl"] += t.get("realized_pnl", 0)
            if t.get("realized_pnl", 0) > 0:
                stats[sym]["wins"] += 1
        for s in stats.values():
            s["win_rate"] = s["wins"] / s["trades"] if s["trades"] > 0 else 0.0
        return stats

    def format_for_prompt(self, max_recent: int = 5) -> str:
        """Format trade track record for PM prompt injection."""
        if not self._trades:
            return "No closed trades yet."

        lines = [
            f"Track record: {self.total_trades} trades, "
            f"{self.win_rate:.0%} win rate, "
            f"avg PnL ${self.avg_pnl:.2f}, "
            f"total PnL ${self.total_pnl:.2f}",
        ]

        if self.avg_winner != 0 or self.avg_loser != 0:
            lines.append(
                f"Avg winner: ${self.avg_winner:.2f}, avg loser: ${self.avg_loser:.2f}"
            )

        sym_stats = self.per_symbol_stats()
        if sym_stats:
            worst = sorted(sym_stats.items(), key=lambda x: x[1]["total_pnl"])[:3]
            best = sorted(sym_stats.items(), key=lambda x: x[1]["total_pnl"], reverse=True)[:3]
            if best:
                lines.append("Best symbols: " + ", ".join(
                    f"{s} (${d['total_pnl']:.0f}, {d['win_rate']:.0%})" for s, d in best
                ))
            if worst and worst[0][1]["total_pnl"] < 0:
                lines.append("Worst symbols: " + ", ".join(
                    f"{s} (${d['total_pnl']:.0f}, {d['win_rate']:.0%})" for s, d in worst
                ))

        recent = self._trades[-max_recent:]
        lines.append(f"\nLast {len(recent)} trades:")
        for t in reversed(recent):
            pnl = t.get("realized_pnl", 0)
            tag = "WIN" if pnl > 0 else "LOSS"
            lines.append(
                f"  {tag}: {t.get('symbol', '?')} "
                f"${pnl:.2f} "
                f"(entry={t.get('entry_price', 0):.2f} → exit={t.get('exit_price', 0):.2f}, "
                f"conviction={t.get('conviction', 0.5):.1f})"
            )

        return "\n".join(lines)

    def to_state_dict(self) -> dict:
        """Serialize for memory persistence."""
        return {
            "pod_id": self._pod_id,
            "trades": self._trades,
        }

    @classmethod
    def load_from_state(cls, state: dict) -> TradeOutcomeTracker:
        """Restore from persisted state."""
        tracker = cls(pod_id=state.get("pod_id", "unknown"))
        tracker._trades = state.get("trades", [])
        return tracker
