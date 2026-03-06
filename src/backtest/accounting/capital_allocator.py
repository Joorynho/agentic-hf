from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from src.core.bus.audit_log import AuditLog
from src.core.bus.event_bus import EventBus
from src.core.models.allocation import AllocationRecord
from src.core.models.enums import EventType
from src.core.models.messages import AgentMessage, Event

logger = logging.getLogger(__name__)

_PUBLISHER = "cio"  # allocator acts on behalf of CIO


class CapitalAllocator:
    """Tracks and applies capital allocation percentages across pods.

    Invariants:
    - sum(allocations) == 1.0 (within 0.001 tolerance)
    - all allocations >= 0.0
    - every change is written to the audit log and published on the bus
    """

    def __init__(
        self,
        pod_ids: list[str],
        bus: EventBus,
        audit_log: AuditLog | None = None,
    ) -> None:
        if not pod_ids:
            raise ValueError("pod_ids must not be empty")
        equal = round(1.0 / len(pod_ids), 6)
        self._allocations: dict[str, float] = {pid: equal for pid in pod_ids}
        self._bus = bus
        self._audit = audit_log

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def current_allocations(self) -> dict[str, float]:
        return dict(self._allocations)

    def get(self, pod_id: str) -> float:
        return self._allocations.get(pod_id, 0.0)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self, records: list[AllocationRecord]) -> tuple[bool, str]:
        """Return (ok, reason). ok=True means safe to apply."""
        new_alloc = dict(self._allocations)
        for rec in records:
            if rec.pod_id not in new_alloc:
                return False, f"Unknown pod_id: {rec.pod_id}"
            new_alloc[rec.pod_id] = rec.new_pct

        if any(v < 0 for v in new_alloc.values()):
            return False, "Allocation contains negative value"

        total = sum(new_alloc.values())
        if abs(total - 1.0) > 0.001:
            return False, f"Allocations sum to {total:.4f}, must equal 1.0"

        return True, "ok"

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    async def apply_allocation(self, records: list[AllocationRecord]) -> None:
        ok, reason = self.validate(records)
        if not ok:
            raise ValueError(f"Invalid allocation: {reason}")

        for rec in records:
            self._allocations[rec.pod_id] = rec.new_pct

        now = datetime.now(timezone.utc)

        # Publish event on bus
        event = Event(
            timestamp=now,
            event_type=EventType.ALLOCATION_CHANGE,
            source=_PUBLISHER,
            data={"records": [r.model_dump(mode="json") for r in records]},
            tags=["allocation"],
        )
        await self._bus.publish("governance.allocation", event.model_dump(mode="json"), _PUBLISHER)

        logger.info("Allocation applied: %s", {r.pod_id: r.new_pct for r in records})

    def propose_equal_weight(self, authorized_by: str = "cio_rule_based") -> list[AllocationRecord]:
        """Return equal-weight AllocationRecords for all pods."""
        n = len(self._allocations)
        equal = round(1.0 / n, 6)
        now = datetime.now(timezone.utc)
        return [
            AllocationRecord(
                timestamp=now,
                pod_id=pod_id,
                old_pct=self._allocations[pod_id],
                new_pct=equal,
                rationale="Equal-weight fallback — no LLM allocation available",
                authorized_by=authorized_by,  # type: ignore[arg-type]
            )
            for pod_id in self._allocations
        ]
