from __future__ import annotations

import time
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

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


class PositionSnapshot(BaseModel):
    """Snapshot of an open position with current market data."""
    symbol: str
    qty: float  # Positive = long, negative = short
    cost_basis: float  # Average cost per share
    current_price: float  # Current market price
    unrealized_pnl: float  # qty * (current_price - cost_basis)

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
