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
    pod_allocations: dict[str, float] = Field(default_factory=dict)  # pod_id -> allocation %
    firm_nav: float = 0.0  # Total firm NAV for notional calculations
    cro_halt: bool = False  # Risk halt flag
    cro_halt_reason: str | None = None  # Why execution was halted
    model_config = {"frozen": True}
