from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from .enums import PodStatus


class PodRiskMetrics(BaseModel):
    pod_id: str
    timestamp: datetime
    nav: float
    daily_pnl: float
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
    error_message: str | None = None
    # NOTE: No positions, signals, or model parameters -- by design

    @property
    def nav(self) -> float:
        """Convenience property to access NAV from risk_metrics."""
        return self.risk_metrics.nav
