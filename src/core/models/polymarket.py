from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class PolymarketSignal(BaseModel):
    market_id: str
    question: str
    yes_price: float  # CLOB best bid for YES token (0-1)
    no_price: float  # CLOB best bid for NO token (0-1)
    implied_prob: float  # yes_price / (yes_price + no_price), normalised
    spread: float  # best ask - best bid
    volume_24h: float
    open_interest: float
    timestamp: datetime
    end_date: Optional[datetime] = None
    tags: list[str] = Field(default_factory=list)
    model_config = {"frozen": True}

    @field_validator("yes_price", "no_price", "implied_prob")
    @classmethod
    def validate_probability(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"Probability must be in [0, 1], got {v}")
        return round(v, 6)
