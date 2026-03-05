from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from .enums import EventType


class AgentMessage(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    timestamp: datetime
    sender: str
    recipient: str
    topic: str
    payload: dict
    correlation_id: UUID | None = None
    model_config = {"frozen": True}


class Event(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    timestamp: datetime
    event_type: EventType
    source: str
    data: dict
    tags: list[str] = Field(default_factory=list)
    model_config = {"frozen": True}
