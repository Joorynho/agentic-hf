from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Bar(BaseModel):
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    adj_close: float | None = None
    source: str
    model_config = {"frozen": True}


class NewsItem(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    timestamp: datetime
    source: str
    headline: str
    url: str = ""
    body_snippet: str = Field(max_length=500)
    entities: list[str] = Field(default_factory=list)
    sentiment: float = Field(ge=-1.0, le=1.0, default=0.0)
    event_tags: list[str] = Field(default_factory=list)
    reliability_score: float = Field(ge=0.0, le=1.0, default=0.5)
    dedupe_hash: str
    model_config = {"frozen": True}
