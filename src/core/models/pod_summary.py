from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from .enums import PodStatus
from .execution import PodPosition


class PodRiskMetrics(BaseModel):
    pod_id: str
    timestamp: datetime
    nav: float
    daily_pnl: float
    realized_pnl: float = 0.0
    starting_capital: float = 0.0
    invested: float = 0.0
    cash: float = 0.0
    drawdown_from_hwm: float
    current_vol_ann: float
    gross_leverage: float
    net_leverage: float
    var_95_1d: float
    es_95_1d: float


class PodExposureBucket(BaseModel):
    asset_class: str
    direction: Literal["long", "short"]
    notional_pct_nav: float


class PodSummary(BaseModel):
    pod_id: str
    timestamp: datetime
    status: PodStatus
    risk_metrics: PodRiskMetrics
    exposure_buckets: list[PodExposureBucket]
    expected_return_estimate: float
    turnover_daily_pct: float
    heartbeat_ok: bool
    positions: list[PodPosition] = Field(default_factory=list)  # Real open positions from PortfolioAccountant
    error_message: str | None = None
    macro_regime: str | None = None          # "risk_on" | "neutral" | "risk_off" | "crisis"
    performance_metrics: dict = Field(default_factory=dict)   # sharpe, sortino, max_drawdown, current_vol, total_return_pct
    trade_outcome_stats: dict = Field(default_factory=dict)   # total_trades, win_rate, avg_pnl, total_pnl, avg_winner, avg_loser

    @property
    def nav(self) -> float:
        """Convenience property to access NAV from risk_metrics."""
        return self.risk_metrics.nav
