from __future__ import annotations

import time
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from typing import Annotated

from pydantic import BaseModel, BeforeValidator, Field

from .enums import OrderType, Side


class Order(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    pod_id: str
    symbol: str
    side: Side
    order_type: OrderType
    quantity: float = Field(gt=0)
    limit_price: float | None = None
    timestamp: datetime
    strategy_tag: str  # pod-internal, never exposed cross-boundary
    conviction: float = 0.5
    model_config = {"frozen": True}


class Fill(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    order_id: UUID
    pod_id: str
    symbol: str
    side: Side
    quantity: float
    price: float
    commission: float
    timestamp: datetime
    model_config = {"frozen": True}


class Position(BaseModel):
    pod_id: str
    symbol: str
    quantity: float
    avg_cost: float
    market_value: float
    unrealised_pnl: float
    last_updated: datetime


class RejectedOrder(BaseModel):
    order_id: UUID
    reason: str
    timestamp: datetime = Field(default_factory=datetime.now)


class RiskApprovalToken(BaseModel):
    pod_id: str
    order_id: UUID
    issued_at_ms: float = Field(default_factory=lambda: time.time() * 1000)
    expires_ms: float = 500.0

    def is_valid(self) -> bool:
        return (time.time() * 1000 - self.issued_at_ms) < self.expires_ms


class OrderResult(BaseModel):
    """Result of order execution on Alpaca."""
    order_id: str | None
    symbol: str
    qty: float
    side: Literal["buy", "sell"]
    status: Literal["FILLED", "PARTIAL", "REJECTED", "PENDING"]
    fill_price: float | None
    fill_qty: float
    reason: str | None = None
    filled_at: datetime | None = None


def _clamp_01(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


ClampedFloat = Annotated[float, BeforeValidator(_clamp_01)]


class TradeProposal(BaseModel):
    """Validated trade proposal from LLM output. Rejects malformed trades."""
    action: Literal["BUY", "SELL"]
    symbol: str
    qty: float = Field(gt=0)
    reasoning: str = ""
    conviction: ClampedFloat = 0.5
    strategy_tag: str = ""
    signal_snapshot: dict = Field(default_factory=dict)
    stop_loss_pct: float = 0.05
    take_profit_pct: float = 0.15
    exit_when: str = ""
    max_hold_days: int = 30


class PositionSnapshot(BaseModel):
    """Snapshot of an open position with current market data."""
    symbol: str
    qty: float  # Positive = long, negative = short
    cost_basis: float  # Average cost per share
    current_price: float  # Current market price
    unrealized_pnl: float  # qty * (current_price - cost_basis)
    entry_thesis: str = ""
    entry_date: str = ""

    @property
    def notional(self) -> float:
        """Notional value of position at current price."""
        return self.qty * self.current_price

    @property
    def pnl_pct(self) -> float:
        """PnL as percentage of cost basis."""
        if self.cost_basis == 0:
            return 0.0
        return (self.current_price - self.cost_basis) / self.cost_basis * 100


class PodPosition(BaseModel):
    """Position model exposed in PodSummary (crosses pod boundary)."""
    symbol: str
    qty: float
    current_price: float
    unrealized_pnl: float = 0.0
    notional: float = 0.0  # qty * current_price
