from __future__ import annotations

from typing import Any


def _as_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _compact_event(event: dict) -> dict:
    return {
        "event_id": str(event.get("event_id") or "")[:80],
        "thread_id": str(event.get("thread_id") or "")[:80],
        "title": str(event.get("title") or "")[:180],
        "summary": str(event.get("summary") or "")[:500],
        "status": str(event.get("status") or "active")[:40],
        "impact_score": event.get("impact_score"),
        "novelty_score": event.get("novelty_score"),
        "confidence": event.get("confidence"),
        "materiality_score": event.get("materiality_score"),
        "direction": event.get("direction") or "mixed",
        "horizon": event.get("horizon") or "",
        "horizon_start": event.get("horizon_start") or "",
        "horizon_end": event.get("horizon_end") or "",
        "transmission_path": str(event.get("transmission_path") or "")[:420],
        "uncertainty": str(event.get("uncertainty") or "")[:360],
        "routing_reason": event.get("routing_reason") if isinstance(event.get("routing_reason"), dict) else {},
        "factors": _as_list(event.get("factors"))[:8],
        "affected_symbols": _as_list(event.get("affected_symbols"))[:10],
        "suggested_specialists": _as_list(event.get("suggested_specialists"))[:5],
        "source_refs": _as_list(event.get("source_refs"))[:5],
    }


def catalyst_events_from_context(features: dict | None, namespace=None, limit: int = 8) -> list[dict]:
    """Return top CatalystEvent dictionaries from signal features or namespace."""
    features = features or {}
    raw = features.get("foresight_events") or features.get("catalyst_events")
    if not raw and namespace is not None:
        try:
            raw = namespace.get("foresight_events") or namespace.get("catalyst_events")
        except Exception:
            raw = []
    events = [_compact_event(e) for e in _as_list(raw) if isinstance(e, dict)]
    events.sort(
        key=lambda e: (
            float(e.get("impact_score") or 0.0),
            float(e.get("confidence") or 0.0),
            float(e.get("novelty_score") or 0.0),
        ),
        reverse=True,
    )
    return events[:limit]


def specialist_briefs_from_context(features: dict | None, namespace=None, limit: int = 8) -> list[dict]:
    """Return recent specialist briefs available to the PM."""
    features = features or {}
    raw = features.get("specialist_briefs")
    if not raw and namespace is not None:
        try:
            raw = namespace.get("specialist_briefs")
        except Exception:
            raw = []
    briefs: list[dict] = []
    for brief in _as_list(raw):
        if not isinstance(brief, dict):
            continue
        briefs.append({
            "brief_id": str(brief.get("brief_id") or "")[:80],
            "type": str(brief.get("type") or "")[:60],
            "symbol": str(brief.get("symbol") or "")[:40],
            "question": str(brief.get("question") or "")[:220],
            "conclusion": str(brief.get("conclusion") or "")[:700],
            "supporting_evidence": [str(x)[:260] for x in _as_list(brief.get("supporting_evidence"))[:5]],
            "opposing_evidence": [str(x)[:260] for x in _as_list(brief.get("opposing_evidence"))[:5]],
            "confidence": brief.get("confidence"),
            "invalidation": str(brief.get("invalidation") or "")[:300],
            "source_refs": _as_list(brief.get("source_refs"))[:5],
        })
    return briefs[:limit]


def prior_reports_from_context(namespace=None, limit: int = 6) -> list[dict]:
    raw = []
    if namespace is not None:
        try:
            raw = namespace.get("prior_reports") or []
        except Exception:
            raw = []
    reports: list[dict] = []
    for report in _as_list(raw):
        if not isinstance(report, dict):
            continue
        reports.append({
            "report_id": str(report.get("report_id") or "")[:80],
            "report_type": str(report.get("report_type") or "")[:80],
            "symbol": str(report.get("symbol") or "")[:40],
            "title": str(report.get("title") or "")[:180],
            "summary": str(report.get("summary") or "")[:500],
            "quality_flags": _as_list(report.get("quality_flags"))[:6],
            "related_catalyst_ids": _as_list(report.get("related_catalyst_ids"))[:6],
        })
    return reports[:limit]


def format_pm_research_sections(features: dict | None, namespace=None) -> list[str]:
    """Prompt sections shared by PM agents for catalysts and specialist briefs."""
    sections: list[str] = []
    catalysts = catalyst_events_from_context(features, namespace)
    if catalysts:
        sections.append("\n## Foresight / Catalyst Ledger")
        sections.append(
            "  Treat these as the primary focus list. A trade can still be non-catalyst-driven, "
            "but then say so explicitly and explain why raw evidence is enough."
        )
        for event in catalysts:
            bits = []
            if event.get("direction"):
                bits.append(f"dir={event['direction']}")
            if event.get("horizon"):
                bits.append(f"horizon={event['horizon']}")
            if event.get("impact_score") is not None:
                bits.append(f"impact={float(event.get('impact_score') or 0.0):.2f}")
            if event.get("confidence") is not None:
                bits.append(f"conf={float(event.get('confidence') or 0.0):.2f}")
            if event.get("materiality_score") is not None:
                bits.append(f"mat={float(event.get('materiality_score') or 0.0):.2f}")
            if event.get("status"):
                bits.append(f"state={event.get('status')}")
            factors = ", ".join(event.get("factors") or [])
            symbols = ", ".join(event.get("affected_symbols") or [])
            specialists = ", ".join(event.get("suggested_specialists") or [])
            sections.append(f"  - {event['event_id']}: {event['title']} ({'; '.join(bits)})")
            if event.get("summary"):
                sections.append(f"    Summary: {event['summary']}")
            if factors:
                sections.append(f"    Factors: {factors}")
            if symbols:
                sections.append(f"    Symbols: {symbols}")
            if specialists:
                sections.append(f"    Suggested specialists: {specialists}")
            if event.get("transmission_path"):
                sections.append(f"    Transmission: {event['transmission_path']}")
            if event.get("uncertainty"):
                sections.append(f"    Uncertainty: {event['uncertainty']}")
        sections.append(
            "  If you trade, include catalyst_ids and catalyst_reasoning. If you HOLD despite relevant "
            "events, include ignored_catalysts with why they are not tradeable yet."
        )

    briefs = specialist_briefs_from_context(features, namespace)
    if briefs:
        sections.append("\n## Specialist Briefs")
        sections.append("  These are advisory. You still own the final PM decision.")
        for brief in briefs:
            support = "; ".join(brief.get("supporting_evidence") or [])
            oppose = "; ".join(brief.get("opposing_evidence") or [])
            sections.append(
                f"  - {brief['type']} {brief.get('symbol') or ''}: {brief.get('conclusion', '')} "
                f"(conf={float(brief.get('confidence') or 0.0):.2f})"
            )
            if support:
                sections.append(f"    Supports: {support}")
            if oppose:
                sections.append(f"    Pushback: {oppose}")
            if brief.get("invalidation"):
                sections.append(f"    Invalidation: {brief['invalidation']}")

    reports = prior_reports_from_context(namespace)
    if reports:
        sections.append("\n## Prior Report Corpus")
        sections.append("  Use these as memory. Do not repeat known weak thesis patterns.")
        for report in reports:
            flags = ", ".join(report.get("quality_flags") or [])
            cats = ", ".join(report.get("related_catalyst_ids") or [])
            sections.append(
                f"  - {report.get('report_type')} {report.get('symbol') or ''}: "
                f"{report.get('title')} - {report.get('summary')}"
            )
            if flags:
                sections.append(f"    Quality flags: {flags}")
            if cats:
                sections.append(f"    Catalyst IDs: {cats}")

    return sections


def pm_context_output_instruction() -> str:
    return (
        "\n\nOptional but strongly encouraged top-level JSON fields:\n"
        '- "catalyst_ids": ["event_id"], for catalysts used in the decision\n'
        '- "catalyst_reasoning": "why the catalyst is or is not tradeable now"\n'
        '- "ignored_catalysts": [{"event_id": "...", "reason": "why HOLD/no trade"}]\n'
        '- "analyst_requests": [{"type": "macro_policy|trend_technical|risk_skeptic|'
        'positioning_flows|asset_fundamental|crypto_onchain|commodity_supply_demand|fx_rates_policy", '
        '"symbol": "TICKER", "question": "...", "reason": "...", '
        '"related_catalyst_ids": ["event_id"], "decision_impact": "what answer changes", '
        '"required_data": "specific data needed"}]\n'
        '- "thesis_fields": {"current_price": "...", "catalyst": "...", "facts_checked": ["..."], '
        '"assumptions": ["..."], "why_now": "...", "valuation_evidence": "...", '
        '"timeframe": "...", "invalidation": "...", "stop_take_profit_logic": "...", '
        '"missing_evidence": ["..."]}\n'
        "Only request specialists when the answer could change the trade. Max 3 requests."
    )


def normalize_pm_context_fields(decision: dict, trades: list[dict], features: dict | None = None) -> dict:
    """Extract catalyst/specialist context from PM JSON and attach it to trades."""
    features = features or {}
    available_events = catalyst_events_from_context(features, None, limit=20)
    available_ids = {event["event_id"] for event in available_events if event.get("event_id")}

    catalyst_ids = [
        str(x) for x in _as_list(decision.get("catalyst_ids"))
        if str(x).strip()
    ][:8]
    if not catalyst_ids and len(available_ids) == 1:
        catalyst_ids = list(available_ids)

    catalyst_reasoning = str(decision.get("catalyst_reasoning") or "").strip()
    ignored_catalysts = [
        item for item in _as_list(decision.get("ignored_catalysts"))
        if isinstance(item, dict)
    ][:10]
    analyst_requests = [
        item for item in _as_list(decision.get("analyst_requests"))
        if isinstance(item, dict)
    ][:6]

    for trade in trades:
        if not isinstance(trade, dict):
            continue
        if catalyst_ids and not trade.get("catalyst_ids"):
            trade["catalyst_ids"] = catalyst_ids
        if catalyst_reasoning and not trade.get("catalyst_reasoning"):
            trade["catalyst_reasoning"] = catalyst_reasoning
        if isinstance(decision.get("thesis_fields"), dict) and not trade.get("thesis_fields"):
            trade["thesis_fields"] = decision.get("thesis_fields")

    return {
        "catalyst_ids": catalyst_ids,
        "catalyst_reasoning": catalyst_reasoning,
        "ignored_catalysts": ignored_catalysts,
        "analyst_requests": analyst_requests,
        "thesis_fields": decision.get("thesis_fields") if isinstance(decision.get("thesis_fields"), dict) else {},
        "available_catalyst_ids": sorted(available_ids),
    }
