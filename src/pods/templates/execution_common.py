"""Shared execution helpers for pod-specific execution traders."""
from __future__ import annotations

from datetime import datetime, timezone

from src.core.models.allocation import MandateUpdate

_GENERIC_REJECTION_REASONS = {
    "",
    "order rejected",
    "rejected",
    "broker rejected",
}


def broker_rejection_reason(result: dict) -> str | None:
    """Return the most useful rejection reason from an adapter result payload."""
    if (result or {}).get("status") != "REJECTED":
        return None
    generic = None
    for key in ("rejection_detail", "reason", "rejection_reason", "error", "message"):
        value = result.get(key)
        if not value:
            continue
        text = str(value).strip()
        if text.lower() not in _GENERIC_REJECTION_REASONS:
            return text
        generic = text
    if generic:
        return generic
    return "Order rejected by Alpaca without a broker reason"


def mandate_allocation_label(mandate: MandateUpdate | None, pod_id: str) -> str | None:
    """Return an allocation label without treating missing mandate data as 0%."""
    if not mandate:
        return None
    if pod_id not in mandate.pod_allocations:
        return "Allocation unknown (pod missing from mandate)"
    return f"Allocation {mandate.pod_allocations[pod_id] * 100:.0f}%"


def store_execution_feedback(namespace, order, result) -> None:
    """Store recent execution failures so PM prompts can avoid repeated dead orders."""
    if getattr(result, "status", None) != "REJECTED":
        return
    feedback = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "symbol": getattr(order, "symbol", ""),
        "side": getattr(getattr(order, "side", None), "value", getattr(order, "side", "")),
        "qty": getattr(order, "quantity", 0.0),
        "stage": getattr(result, "stage", None) or "unknown",
        "reason": getattr(result, "reason", None) or "Rejected without reason",
    }
    try:
        existing = namespace.get("execution_feedback") or []
        existing = [feedback] + list(existing)
        namespace.set("execution_feedback", existing[:10])
    except Exception:
        pass


def execution_feedback_block(namespace) -> str:
    """Render recent execution failures for a PM prompt."""
    try:
        feedback = namespace.get("execution_feedback") or []
    except Exception:
        feedback = []
    if not feedback:
        return ""
    lines = ["## Recent Broker / Execution Feedback"]
    lines.append("Do not repeat rejected orders unless you explicitly fix the broker issue.")
    for item in feedback[:5]:
        lines.append(
            f"  - {str(item.get('side', '')).upper()} {item.get('qty', 0)} {item.get('symbol', '?')}: "
            f"{item.get('stage', 'unknown')} rejection - {item.get('reason', 'No reason')}"
        )
    return "\n".join(lines)
