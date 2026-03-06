from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class AllocationRecord(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    timestamp: datetime
    pod_id: str
    old_pct: float
    new_pct: float
    rationale: str
    authorized_by: Literal["cio_llm", "cio_rule_based"]
    model_config = {"frozen": True}


class MandateUpdate(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    timestamp: datetime
    narrative: str
    objectives: list[str]
    constraints: dict
    rationale: str
    authorized_by: Literal["ceo_llm", "ceo_rule_based"]
    cio_approved: bool = False
    cro_approved: bool = False
    model_config = {"frozen": True}
