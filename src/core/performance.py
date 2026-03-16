"""Pure-function performance analytics — Sharpe, Sortino, max drawdown, rolling Sharpe."""
from __future__ import annotations

import math


def sharpe_ratio(returns: list[float], risk_free: float = 0.0) -> float:
    """Annualized Sharpe ratio from daily returns."""
    if len(returns) < 2:
        return 0.0
    excess = [r - risk_free / 252 for r in returns]
    mean_ex = sum(excess) / len(excess)
    variance = sum((r - mean_ex) ** 2 for r in excess) / (len(excess) - 1)
    std = math.sqrt(variance)
    if std == 0:
        return 0.0
    return (mean_ex / std) * math.sqrt(252)


def sortino_ratio(returns: list[float], risk_free: float = 0.0) -> float:
    """Annualized Sortino ratio (penalizes only downside volatility)."""
    if len(returns) < 2:
        return 0.0
    excess = [r - risk_free / 252 for r in returns]
    mean_ex = sum(excess) / len(excess)
    downside = [r for r in excess if r < 0]
    if not downside:
        return float("inf") if mean_ex > 0 else 0.0
    downside_var = sum(r ** 2 for r in downside) / len(downside)
    downside_std = math.sqrt(downside_var)
    if downside_std == 0:
        return 0.0
    return (mean_ex / downside_std) * math.sqrt(252)


def max_drawdown(nav_series: list[float]) -> float:
    """Worst peak-to-trough drawdown as a negative percentage (e.g. -0.12 = -12%)."""
    if len(nav_series) < 2:
        return 0.0
    peak = nav_series[0]
    worst = 0.0
    for nav in nav_series:
        if nav > peak:
            peak = nav
        dd = (nav - peak) / peak if peak > 0 else 0.0
        if dd < worst:
            worst = dd
    return worst


def rolling_sharpe(returns: list[float], window: int = 20) -> float:
    """Sharpe ratio over the trailing *window* days."""
    if len(returns) < window or window < 2:
        return sharpe_ratio(returns)
    return sharpe_ratio(returns[-window:])
