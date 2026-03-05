from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from .enums import AgentType, TimeHorizon


class RiskBudget(BaseModel):
    target_vol: float = Field(gt=0, lt=1.0)
    max_leverage: float = Field(gt=0, le=10.0)
    max_drawdown: float = Field(gt=0, lt=1.0)
    max_concentration: float = Field(gt=0, le=1.0)
    max_sector_exposure: float = Field(gt=0, le=1.0)
    liquidity_min_adv_pct: float = Field(gt=0, le=1.0)
    var_limit_95: float = Field(gt=0, lt=1.0)
    es_limit_95: float = Field(gt=0, lt=1.0)


class ExecutionConfig(BaseModel):
    style: Literal["passive", "aggressive", "neutral"]
    max_participation_rate: float = Field(gt=0, le=1.0)
    allowed_venues: list[str]
    order_types: list[str]


class BacktestConfig(BaseModel):
    start_date: date
    end_date: date
    min_history_days: int = Field(gt=0)
    walk_forward_folds: int = Field(gt=0)
    latency_ms: int = Field(ge=0)
    tcm_bps: float = Field(ge=0)
    slippage_model: Literal["fixed", "sqrt_impact", "linear"]


class PodConfig(BaseModel):
    pod_id: str
    name: str
    strategy_family: str
    universe: list[str]
    time_horizon: TimeHorizon
    risk_budget: RiskBudget
    execution: ExecutionConfig
    backtest: BacktestConfig
    pm_agent_type: AgentType
    enabled: bool = True
