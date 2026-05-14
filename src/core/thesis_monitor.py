from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from src.core.managed_runtime import new_id, iso_now, parse_ts
from src.core.models.execution import ThesisMonitorResult


def _norm(symbol: str) -> str:
    return str(symbol or "").strip().upper()


def _get(position: Any, name: str, default: Any = None) -> Any:
    if isinstance(position, Mapping):
        return position.get(name, default)
    return getattr(position, name, default)


def _age_days(entry_date: Any) -> float | None:
    ts = parse_ts(entry_date)
    if not ts:
        return None
    return max(0.0, (datetime.now(timezone.utc) - ts).total_seconds() / 86400.0)


def monitor_position_thesis(
    *,
    pod_id: str,
    symbol: str,
    position: Any,
    catalyst_events: list[dict] | None = None,
    latest_regime: str = "",
) -> ThesisMonitorResult:
    sym = _norm(symbol)
    thesis = str(_get(position, "entry_thesis", "") or _get(position, "reasoning", "") or "")
    max_hold_days = int(_get(position, "max_hold_days", 0) or 0)
    age = _age_days(_get(position, "entry_date", "") or _get(position, "opened_at", ""))
    unrealized_pnl = float(_get(position, "unrealized_pnl", _get(position, "unrealised_pnl", 0.0)) or 0.0)
    market_value = abs(float(_get(position, "market_value", 0.0) or 0.0))
    pnl_pct = unrealized_pnl / market_value if market_value > 0 else 0.0

    triggers: list[str] = []
    catalyst_ids: list[str] = []
    status = "THESIS_OK"
    reason = "Thesis monitor found no immediate issue."

    if not thesis.strip():
        triggers.append("missing_thesis")
    elif len(thesis) < 120:
        triggers.append("thin_thesis")

    if max_hold_days and age is not None:
        if age > max_hold_days:
            triggers.append("max_hold_exceeded")
        elif age > max_hold_days * 0.8:
            triggers.append("max_hold_near")

    for event in catalyst_events or []:
        if not isinstance(event, dict):
            continue
        symbols = {_norm(s) for s in event.get("affected_symbols") or []}
        if sym not in symbols and sym not in str(event.get("summary", "") + event.get("title", "")).upper():
            continue
        event_id = str(event.get("event_id") or "")
        if event_id:
            catalyst_ids.append(event_id)
        event_status = str(event.get("status") or "").lower()
        if event_status in {"expired", "reviewed", "ignored"}:
            triggers.append(f"catalyst_{event_status}")
        horizon_end = parse_ts(event.get("horizon_end"))
        if horizon_end and datetime.now(timezone.utc) > horizon_end:
            triggers.append("catalyst_horizon_expired")

    if latest_regime and latest_regime.lower() not in thesis.lower() and any(
        term in thesis.lower() for term in ("regime", "risk-on", "risk-off", "inflation", "rates", "liquidity")
    ):
        triggers.append("regime_needs_refresh")

    if pnl_pct < -0.03 and "invalidation" not in thesis.lower() and "exit if" not in thesis.lower():
        triggers.append("loss_without_clear_invalidation")

    if "missing_thesis" in triggers or "max_hold_exceeded" in triggers or "catalyst_horizon_expired" in triggers:
        status = "ADD_BLOCKED"
        reason = "Position thesis is stale or incomplete; additions are blocked until PM writes a fresh expansion thesis."
    elif "loss_without_clear_invalidation" in triggers:
        status = "REDUCE_RECOMMENDED"
        reason = "Position is losing without clear invalidation language in the stored thesis."
    elif triggers:
        status = "REVIEW_REQUIRED"
        reason = "Position thesis needs review: " + ", ".join(sorted(set(triggers)))

    return ThesisMonitorResult(
        monitor_id=new_id("thesis_monitor"),
        pod_id=pod_id,
        symbol=sym,
        status=status,
        reason=reason,
        triggers=sorted(set(triggers)),
        catalyst_ids=list(dict.fromkeys(catalyst_ids)),
        thesis_age_days=round(age, 2) if age is not None else None,
        max_hold_days=max_hold_days,
        created_at=iso_now(),
    )


def monitor_positions(
    *,
    pod_id: str,
    positions: Mapping[str, Any],
    catalyst_events: list[dict] | None = None,
    latest_regime: str = "",
) -> list[dict]:
    results = []
    for symbol, position in (positions or {}).items():
        results.append(
            monitor_position_thesis(
                pod_id=pod_id,
                symbol=symbol,
                position=position,
                catalyst_events=catalyst_events,
                latest_regime=latest_regime,
            ).model_dump(mode="json")
        )
    return results
