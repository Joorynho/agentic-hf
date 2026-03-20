"""Quantitative pod scoring for CIO governance (25% weight in decision)."""
from __future__ import annotations
from dataclasses import dataclass

WEIGHTS = {"sharpe": 0.40, "max_drawdown": 0.30, "win_rate": 0.20, "total_return": 0.10}

_SHARPE_RANGE   = (-2.0, 4.0)
_DD_RANGE       = (-0.50, 0.0)   # less negative = better
_WINRATE_RANGE  = (0.0, 1.0)
_RETURN_RANGE   = (-0.30, 0.30)


def _norm(value: float, lo: float, hi: float) -> float:
    if hi == lo:
        return 0.5
    return max(0.0, min(1.0, (value - lo) / (hi - lo)))


@dataclass
class PodScore:
    pod_id: str
    score: float
    sharpe_norm: float
    drawdown_norm: float
    win_rate_norm: float
    return_norm: float

    def scorecard_row(self) -> str:
        bar = "█" * int(self.score * 10) + "░" * (10 - int(self.score * 10))
        return (
            f"  {self.pod_id:<14} [{bar}] {self.score:.2f}  "
            f"sharpe={self.sharpe_norm:.2f}  dd={self.drawdown_norm:.2f}  "
            f"wr={self.win_rate_norm:.2f}  ret={self.return_norm:.2f}"
        )


def score_pod(pod_id: str, perf: dict, trade_stats: dict) -> PodScore:
    sharpe   = float(perf.get("sharpe") or 0.0)
    max_dd   = float(perf.get("max_drawdown") or 0.0)
    win_rate = float(trade_stats.get("win_rate") or 0.5)
    ret      = float(perf.get("total_return_pct") or 0.0)

    sn = _norm(sharpe,   *_SHARPE_RANGE)
    dn = _norm(max_dd,   *_DD_RANGE)
    wn = _norm(win_rate, *_WINRATE_RANGE)
    rn = _norm(ret,      *_RETURN_RANGE)

    composite = (
        WEIGHTS["sharpe"]       * sn +
        WEIGHTS["max_drawdown"] * dn +
        WEIGHTS["win_rate"]     * wn +
        WEIGHTS["total_return"] * rn
    )
    return PodScore(pod_id, composite, sn, dn, wn, rn)


def format_scorecard(scores: list[PodScore]) -> str:
    ranked = sorted(scores, key=lambda s: s.score, reverse=True)
    header = (
        "╔══ QUANTITATIVE SCORECARD ══════════════════════════════════════════════╗\n"
        "║ Weights: Sharpe×0.40 | MaxDrawdown×0.30 | WinRate×0.20 | Return×0.10  ║\n"
        "╠═════════════════════════════════════════════════════════════════════════╣"
    )
    rows = "\n".join(s.scorecard_row() for s in ranked)
    footer = (
        "╠═════════════════════════════════════════════════════════════════════════╣\n"
        "║ NOTE: This scorecard is supporting evidence only (25% weight).          ║\n"
        "║ Your qualitative assessment drives the decision (75%).                   ║\n"
        "╚═════════════════════════════════════════════════════════════════════════╝"
    )
    return f"{header}\n{rows}\n{footer}"
