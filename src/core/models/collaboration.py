from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from .messages import AgentMessage


class CollaborationLoop(BaseModel):
    loop_id: UUID = Field(default_factory=uuid4)
    topic: str
    participants: list[str]  # agent IDs
    max_iterations: int
    messages: list[AgentMessage] = Field(default_factory=list)
    consensus_reached: bool = False
    outcome: dict = Field(default_factory=dict)
    iterations_used: int = 0
    started_at: datetime
    completed_at: datetime | None = None
    # Not frozen — built up incrementally during the loop
