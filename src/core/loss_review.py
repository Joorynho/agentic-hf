"""Pod loss-review and risk-intervention helpers.

This module is intentionally asset-class agnostic. It looks at NAV,
open-position P&L, and closed-trade P&L; the caller decides how to feed the
result into PM/CRO/CIO workflows.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable


POD_WATCH_LOSS_PCT = -0.0075
POD_RESTRICT_LOSS_PCT = -0.0125
POD_PAUSE_LOSS_PCT = -0.0200

CONTRIBUTOR_WATCH_NAV_IMPACT = -0.0040
CONTRIBUTOR_RESTRICT_NAV_IMPACT = -0.0075
CONTRIBUTOR_PAUSE_NAV_IMPACT = -0.0125


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        ts = value
    else:
        try:
            ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def _fmt_pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def _open_contributors(
    positions: Iterable[Any],
    baseline_nav: float,
) -> list[dict]:
    contributors: list[dict] = []
    for pos in positions:
        symbol = str(_get(pos, "symbol", "") or "").upper()
        if not symbol:
            continue
        qty = _float(_get(pos, "qty", _get(pos, "quantity", 0.0)))
        cost_basis = _float(_get(pos, "cost_basis", _get(pos, "avg_entry", 0.0)))
        current_price = _float(_get(pos, "current_price", _get(pos, "price", 0.0)))
        unrealized = _float(_get(pos, "unrealized_pnl", _get(pos, "unrl_pnl", 0.0)))
        cost_notional = abs(qty * cost_basis)
        current_notional = abs(qty * current_price)
        contributors.append({
            "symbol": symbol,
            "source": "open_position",
            "pnl": unrealized,
            "pnl_pct": unrealized / cost_notional if cost_notional > 0 else 0.0,
            "nav_impact_pct": unrealized / baseline_nav if baseline_nav > 0 else 0.0,
            "qty": qty,
            "notional": current_notional,
            "entry_price": cost_basis,
            "current_price": current_price,
            "thesis": str(_get(pos, "entry_thesis", "") or ""),
        })
    return contributors


def _closed_contributors(
    closed_trades: Iterable[dict],
    baseline_nav: float,
    now: datetime,
) -> list[dict]:
    today = now.astimezone(timezone.utc).date()
    contributors: list[dict] = []
    for trade in closed_trades:
        exit_ts = _parse_ts(
            trade.get("exit_time")
            or trade.get("exit_date")
            or trade.get("closed_at")
            or trade.get("timestamp")
        )
        if not exit_ts or exit_ts.date() != today:
            continue
        realized = _float(trade.get("realized_pnl") or trade.get("pnl") or trade.get("pnl_usd"))
        entry_price = _float(trade.get("entry_price"))
        qty = _float(trade.get("qty") or trade.get("quantity"))
        cost_notional = abs(qty * entry_price)
        symbol = str(trade.get("symbol", "") or "").upper()
        if not symbol:
            continue
        contributors.append({
            "symbol": symbol,
            "source": "closed_trade",
            "pnl": realized,
            "pnl_pct": realized / cost_notional if cost_notional > 0 else 0.0,
            "nav_impact_pct": realized / baseline_nav if baseline_nav > 0 else 0.0,
            "qty": qty,
            "notional": cost_notional,
            "entry_price": entry_price,
            "current_price": _float(trade.get("exit_price")),
            "thesis": str(trade.get("entry_thesis") or trade.get("entry_reasoning") or ""),
            "exit_time": exit_ts.isoformat() if exit_ts else "",
        })
    return contributors


def _classify(
    daily_pnl_pct: float,
    worst_nav_impact: float,
) -> tuple[str, str, str, bool]:
    if daily_pnl_pct <= POD_PAUSE_LOSS_PCT or worst_nav_impact <= CONTRIBUTOR_PAUSE_NAV_IMPACT:
        return "paused", "critical", "pause_pod", True
    if daily_pnl_pct <= POD_RESTRICT_LOSS_PCT or worst_nav_impact <= CONTRIBUTOR_RESTRICT_NAV_IMPACT:
        return "restricted", "warning", "restrict_new_risk", True
    if daily_pnl_pct <= POD_WATCH_LOSS_PCT or worst_nav_impact <= CONTRIBUTOR_WATCH_NAV_IMPACT:
        return "watch", "warning", "review_required", False
    return "clear", "info", "clear", False


def build_loss_review(
    *,
    pod_id: str,
    nav: float,
    starting_capital: float,
    positions: Iterable[Any],
    closed_trades: Iterable[dict],
    baseline_nav: float | None = None,
    now: datetime | None = None,
    iteration: int = 0,
) -> dict:
    """Build a pod loss-review packet and runtime restriction.

    The result is JSON-safe and uses percentage fields as decimals
    (for example, -0.0125 means -1.25%).
    """
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    nav = _float(nav)
    starting_capital = _float(starting_capital) or nav
    baseline = _float(baseline_nav) or starting_capital or nav
    if baseline <= 0:
        baseline = nav if nav > 0 else 1.0

    open_items = _open_contributors(positions, baseline)
    closed_items = _closed_contributors(closed_trades, baseline, now)
    contributors = sorted(
        [item for item in open_items + closed_items if item.get("pnl", 0.0) < 0.0],
        key=lambda item: item.get("nav_impact_pct", 0.0),
    )

    open_unrealized = sum(_float(item.get("pnl")) for item in open_items)
    realized_today = sum(_float(item.get("pnl")) for item in closed_items)
    daily_pnl = nav - baseline
    daily_pnl_pct = daily_pnl / baseline if baseline > 0 else 0.0
    worst_nav_impact = contributors[0]["nav_impact_pct"] if contributors else 0.0

    status, severity, action, block_new_risk = _classify(daily_pnl_pct, worst_nav_impact)
    triggered = status != "clear"

    reasons: list[str] = []
    if daily_pnl_pct <= POD_WATCH_LOSS_PCT:
        reasons.append(f"Pod daily P&L is {_fmt_pct(daily_pnl_pct)} versus review threshold {_fmt_pct(POD_WATCH_LOSS_PCT)}")
    if contributors and worst_nav_impact <= CONTRIBUTOR_WATCH_NAV_IMPACT:
        worst = contributors[0]
        reasons.append(
            f"{worst['symbol']} contributed {_fmt_pct(worst_nav_impact)} of pod NAV "
            f"({worst['source'].replace('_', ' ')})"
        )
    if not reasons:
        reasons.append("No loss threshold currently breached")

    if triggered:
        top_txt = ", ".join(
            f"{item['symbol']} {item['pnl']:+.2f} ({_fmt_pct(item['nav_impact_pct'])} NAV)"
            for item in contributors[:3]
        ) or "no single negative contributor identified"
        pm_defense = (
            "PM review required: explain whether the original thesis still holds, "
            f"why the drawdown is temporary or structural, and what should change for {top_txt}. "
            "Include current macro/news/regime changes, entry trigger status, invalidation status, "
            "and whether the right action is hold, trim, exit, or wait."
        )
    else:
        pm_defense = "No PM defense required; pod is inside daily loss thresholds."

    cro_action_map = {
        "clear": "CRO action: no intervention.",
        "review_required": "CRO action: require PM defense before adding to losing exposure.",
        "restrict_new_risk": "CRO action: reduce-only mode. Block new risk-increasing orders; allow holds and risk-reducing exits.",
        "pause_pod": "CRO action: pause new risk. Only risk-reducing orders are allowed until CIO/CRO review clears the pod.",
    }
    cio_map = {
        "clear": "CIO decision: no escalation needed.",
        "review_required": "CIO provisional decision: watch the pod and require a fresh thesis before any expansion.",
        "restrict_new_risk": "CIO provisional decision: restrict the pod to risk reduction until the loss drivers are explained.",
        "pause_pod": "CIO provisional decision: pause new exposure and prioritize de-risking or thesis invalidation review.",
    }

    restriction = {
        "mode": "reduce_only" if block_new_risk else "normal",
        "block_new_risk": block_new_risk,
        "allow_reductions": True,
        "reason": "; ".join(reasons),
        "action": action,
        "severity": severity,
        "set_at": now.isoformat(),
    }

    return {
        "pod_id": pod_id,
        "status": status,
        "severity": severity,
        "triggered": triggered,
        "action": action,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "iteration": iteration,
        "baseline_nav": round(baseline, 4),
        "current_nav": round(nav, 4),
        "starting_capital": round(starting_capital, 4),
        "daily_pnl": round(daily_pnl, 4),
        "daily_pnl_pct": daily_pnl_pct,
        "realized_today": round(realized_today, 4),
        "open_unrealized_pnl": round(open_unrealized, 4),
        "worst_nav_impact_pct": worst_nav_impact,
        "trigger_reason": "; ".join(reasons),
        "top_contributors": contributors[:5],
        "pm_defense_prompt": pm_defense,
        "cro_action": cro_action_map[action],
        "cio_decision": cio_map[action],
        "restriction": restriction,
        "next_review_at": (now + timedelta(minutes=30)).isoformat(),
        "thresholds": {
            "pod_watch_loss_pct": POD_WATCH_LOSS_PCT,
            "pod_restrict_loss_pct": POD_RESTRICT_LOSS_PCT,
            "pod_pause_loss_pct": POD_PAUSE_LOSS_PCT,
            "contributor_watch_nav_impact": CONTRIBUTOR_WATCH_NAV_IMPACT,
            "contributor_restrict_nav_impact": CONTRIBUTOR_RESTRICT_NAV_IMPACT,
            "contributor_pause_nav_impact": CONTRIBUTOR_PAUSE_NAV_IMPACT,
        },
    }


def format_loss_review_for_prompt(review: dict) -> str:
    """Compact prompt text for PM agents."""
    if not review or review.get("status") == "clear":
        return ""
    contributors = review.get("top_contributors") or []
    lines = [
        f"Pod: {str(review.get('pod_id', '')).upper()}",
        f"Status: {str(review.get('status', '')).upper()}",
        f"Reason: {review.get('trigger_reason', '')}",
        f"Restriction: {review.get('cro_action', '')}",
        f"CIO: {review.get('cio_decision', '')}",
    ]
    for item in contributors[:3]:
        lines.append(
            f"Contributor: {item.get('symbol')} {item.get('pnl', 0):+.2f} "
            f"({_fmt_pct(_float(item.get('nav_impact_pct')))} NAV impact)"
        )
    lines.append(str(review.get("pm_defense_prompt", "")))
    return "\n".join(line for line in lines if line)
