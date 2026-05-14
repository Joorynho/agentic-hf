from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from src.core.models.execution import CatalystEvent
from src.core.research_feed import ResearchFeedStore, classify_research_item

logger = logging.getLogger(__name__)


POD_IDS = ("equities", "fx", "crypto", "commodities")

_FACTOR_PODS: dict[str, tuple[str, ...]] = {
    "inflation": ("fx", "commodities", "equities"),
    "rates": ("fx", "equities", "crypto", "commodities"),
    "real_yields": ("commodities", "fx", "crypto"),
    "usd": ("fx", "commodities", "crypto", "equities"),
    "energy": ("commodities", "equities", "fx"),
    "metals": ("commodities", "fx"),
    "geopolitics": ("commodities", "fx", "equities", "crypto"),
    "risk_sentiment": ("equities", "crypto", "fx", "commodities"),
    "credit": ("equities", "fx", "crypto"),
    "crypto_liquidity": ("crypto", "equities"),
    "earnings": ("equities",),
}

_ASSET_TO_PODS: dict[str, tuple[str, ...]] = {
    "equities": ("equities",),
    "fx": ("fx",),
    "crypto": ("crypto",),
    "commodities": ("commodities",),
    "macro": POD_IDS,
}

_SPECIALIST_BY_FACTOR: dict[str, str] = {
    "inflation": "macro_policy",
    "rates": "macro_policy",
    "real_yields": "macro_policy",
    "usd": "fx_rates_policy",
    "energy": "commodity_supply_demand",
    "metals": "commodity_supply_demand",
    "geopolitics": "risk_skeptic",
    "risk_sentiment": "risk_skeptic",
    "credit": "risk_skeptic",
    "crypto_liquidity": "crypto_onchain",
    "earnings": "asset_fundamental",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_key(*parts: object) -> str:
    raw = "|".join(str(part or "") for part in parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:20]


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(value)))


def _jsonable_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


class ForesightService:
    """Builds an advisory catalyst ledger from shared research inputs.

    This service is deliberately not an execution trigger. It ranks and routes
    potentially important events so PMs have a focused research layer before
    they decide whether deeper specialist analysis or trades are warranted.
    """

    def __init__(self, feed_store: ResearchFeedStore | None = None) -> None:
        self._feed_store = feed_store or ResearchFeedStore(":memory:")
        self._last_fred_snapshot: dict[str, Any] = {}
        self._last_generated_at: str | None = None
        self._last_summary: dict[str, Any] = {
            "status": "UNKNOWN",
            "events": [],
            "counts": {"active": 0, "stale": 0, "failed": 0},
        }

    @property
    def feed_store(self) -> ResearchFeedStore:
        return self._feed_store

    def refresh(self, shared_data: dict | None, pod_contexts: dict[str, dict] | None = None) -> dict:
        shared_data = shared_data or {}
        pod_contexts = pod_contexts or {}
        events: list[CatalystEvent] = []

        try:
            for item in self._feed_store.get_items(limit=120):
                event = self._event_from_feed_item(item, pod_contexts)
                if event:
                    events.append(event)
        except Exception as exc:
            logger.debug("[foresight] Feed item scan failed: %s", exc)

        for signal in shared_data.get("poly_signals") or []:
            event = self._event_from_polymarket(signal, pod_contexts)
            if event:
                events.append(event)

        macro_event = self._event_from_macro(shared_data.get("fred_snapshot") or {})
        if macro_event:
            events.append(macro_event)

        events.sort(key=lambda e: (e.impact_score, e.confidence, e.novelty_score), reverse=True)
        events = self._thread_events(self._dedupe_events(events))[:75]

        try:
            self._feed_store.record_catalyst_events([e.model_dump(mode="json") for e in events], ts=_now())
        except Exception as exc:
            logger.debug("[foresight] Catalyst persistence failed: %s", exc)

        self._last_generated_at = _now().isoformat()
        self._last_summary = self._build_report(events=events, limit=75)
        return self._last_summary

    def get_report(self, limit: int = 100, pod_id: str | None = None) -> dict:
        try:
            events = self._feed_store.get_catalyst_events(limit=limit, pod_id=pod_id)
        except Exception as exc:
            logger.debug("[foresight] Catalyst read failed: %s", exc)
            events = list(self._last_summary.get("events") or [])[:limit]
            if pod_id:
                events = [
                    e for e in events
                    if pod_id.lower() in [str(p).lower() for p in e.get("affected_pods", [])]
                ]
        return self._build_report(events=events, limit=limit)

    def _build_report(self, events: list[Any], limit: int = 100) -> dict:
        rows: list[dict] = []
        for event in events[:limit]:
            if hasattr(event, "model_dump"):
                rows.append(event.model_dump(mode="json"))
            elif isinstance(event, dict):
                rows.append(dict(event))
        counts = {state: 0 for state in ("new", "active", "acted_on", "ignored", "expired", "reviewed", "stale", "failed")}
        for event in rows:
            state = str(event.get("status", "active") or "active").lower()
            counts[state] = counts.get(state, 0) + 1
        by_pod = {pod: 0 for pod in POD_IDS}
        for event in rows:
            for pod in event.get("affected_pods", []) or []:
                if pod in by_pod:
                    by_pod[pod] += 1
        return {
            "status": "OK" if rows else "EMPTY",
            "generated_at": _now().isoformat(),
            "events": rows,
            "counts": counts,
            "by_pod": by_pod,
            "event_count": len(rows),
        }

    def _event_from_feed_item(self, item: dict, pod_contexts: dict[str, dict]) -> CatalystEvent | None:
        title = str(item.get("title") or item.get("text") or "").strip()
        if not title:
            return None
        item_key = str(item.get("item_key") or _hash_key(title, item.get("url")))
        factors = _jsonable_list(item.get("factors"))
        tickers = _jsonable_list(item.get("tickers"))
        asset_classes = _jsonable_list(item.get("asset_classes"))
        pods = self._route_pods(asset_classes=asset_classes, factors=factors, symbols=tickers, pod_contexts=pod_contexts)
        if not pods:
            pods = list(POD_IDS)
        impact = _clamp(float(item.get("urgency") or 0.35))
        novelty = self._novelty_from_item(item)
        confidence = _clamp(0.45 + 0.10 * len(factors) + (0.10 if item.get("url") else 0.0))
        direction = self._direction_from_text(title + " " + str(item.get("text") or ""), item.get("sentiment"))
        return self._enrich_event(CatalystEvent(
            event_id=f"feed:{item_key}",
            title=title[:180],
            summary=str(item.get("text") or title)[:700],
            source_refs=[{
                "source": item.get("source") or "research_feed",
                "url": item.get("url") or "",
                "published_at": item.get("published_at") or "",
            }],
            novelty_score=novelty,
            impact_score=impact,
            confidence=confidence,
            affected_pods=pods,
            affected_symbols=sorted({str(s).upper() for s in tickers if s}),
            factors=sorted({str(f) for f in factors if f}),
            direction=direction,
            horizon="immediate" if impact >= 0.75 else "days",
            suggested_specialists=self._suggest_specialists(factors, pods),
            status="active",
            created_at=_now(),
        ), pod_contexts=pod_contexts)

    def _event_from_polymarket(self, signal: dict, pod_contexts: dict[str, dict]) -> CatalystEvent | None:
        if not isinstance(signal, dict):
            return None
        question = str(signal.get("question") or signal.get("market") or "").strip()
        if not question:
            return None
        routing = classify_research_item({"title": question, "text": question, "category": "prediction"})
        factors = routing["factors"]
        symbols = routing["tickers"]
        pods = self._route_pods(routing["asset_classes"], factors, symbols, pod_contexts)
        probability = float(signal.get("implied_prob") or signal.get("probability") or 0.5)
        volume = float(signal.get("volume_24h") or signal.get("volume") or 0.0)
        impact = _clamp(0.35 + abs(probability - 0.5) * 0.55 + min(volume / 1_000_000, 0.25))
        return self._enrich_event(CatalystEvent(
            event_id=f"poly:{_hash_key(question)}",
            title=f"Prediction market: {question[:150]}",
            summary=f"Polymarket probability is {probability:.0%}; use as research context, not a standalone trade trigger.",
            source_refs=[{"source": "Polymarket", "url": signal.get("url") or signal.get("market_url") or ""}],
            novelty_score=0.55,
            impact_score=impact,
            confidence=_clamp(0.45 + min(volume / 2_000_000, 0.25)),
            affected_pods=pods or list(POD_IDS),
            affected_symbols=sorted({str(s).upper() for s in symbols}),
            factors=sorted({str(f) for f in factors}),
            direction="mixed",
            horizon="days",
            suggested_specialists=self._suggest_specialists(factors, pods),
            status="active",
            created_at=_now(),
        ), pod_contexts=pod_contexts)

    def _event_from_macro(self, fred: dict) -> CatalystEvent | None:
        if not fred:
            return None
        factors: list[str] = []
        summary_bits: list[str] = []
        vix = self._num(fred.get("VIXCLS"))
        curve = self._num(fred.get("T10Y2Y"))
        tips = self._num(fred.get("DFII10"))
        dgs10 = self._num(fred.get("DGS10"))
        if vix is not None and vix >= 25:
            factors.append("risk_sentiment")
            summary_bits.append(f"VIX elevated at {vix:.1f}")
        if curve is not None and curve < -0.20:
            factors.extend(["rates", "credit"])
            summary_bits.append(f"10Y-2Y curve inverted at {curve:.2f}")
        if tips is not None and tips > 1.0:
            factors.append("real_yields")
            summary_bits.append(f"10Y real-yield proxy positive at {tips:.2f}%")
        previous = self._last_fred_snapshot or {}
        if dgs10 is not None and previous.get("DGS10") is not None:
            prev10 = self._num(previous.get("DGS10"))
            if prev10 is not None and abs(dgs10 - prev10) >= 0.20:
                factors.append("rates")
                summary_bits.append(f"10Y yield moved {dgs10 - prev10:+.2f} pts since last snapshot")
        self._last_fred_snapshot = dict(fred)
        if not factors:
            return None
        factors = sorted(set(factors))
        impact = _clamp(0.45 + 0.12 * len(factors))
        return self._enrich_event(CatalystEvent(
            event_id=f"macro:{_now().date().isoformat()}:{_hash_key(','.join(factors))}",
            title="Macro regime catalyst detected",
            summary="; ".join(summary_bits),
            source_refs=[{"source": "FRED", "url": ""}],
            novelty_score=0.45,
            impact_score=impact,
            confidence=0.70,
            affected_pods=list(POD_IDS),
            affected_symbols=[],
            factors=factors,
            direction="mixed",
            horizon="days",
            suggested_specialists=self._suggest_specialists(factors, list(POD_IDS)),
            status="active",
            created_at=_now(),
        ), pod_contexts={pod: {} for pod in POD_IDS})

    def _enrich_event(self, event: CatalystEvent, pod_contexts: dict[str, dict]) -> CatalystEvent:
        """Attach V2 lifecycle/routing metadata while keeping generation deterministic."""
        now = _now()
        horizon = str(event.horizon or "days").lower()
        if horizon == "immediate":
            horizon_end = now + timedelta(hours=12)
        elif "week" in horizon:
            horizon_end = now + timedelta(days=7)
        elif "month" in horizon:
            horizon_end = now + timedelta(days=30)
        else:
            horizon_end = now + timedelta(days=3)
        thread_id = self._thread_id(event)
        routing_reason = self._routing_reason(event, pod_contexts)
        materiality = _clamp(
            0.45 * float(event.impact_score or 0.0)
            + 0.30 * float(event.confidence or 0.0)
            + 0.15 * float(event.novelty_score or 0.0)
            + 0.10 * min(len(event.affected_pods or []) / len(POD_IDS), 1.0)
        )
        transmission_path = self._transmission_path(event)
        uncertainty = self._uncertainty_note(event)
        return event.model_copy(update={
            "thread_id": thread_id,
            "materiality_score": materiality,
            "horizon_start": event.horizon_start or now,
            "horizon_end": event.horizon_end or horizon_end,
            "routing_reason": routing_reason,
            "transmission_path": event.transmission_path or transmission_path,
            "uncertainty": event.uncertainty or uncertainty,
            "status": event.status or "active",
        })

    def _route_pods(
        self,
        asset_classes: list,
        factors: list,
        symbols: list,
        pod_contexts: dict[str, dict],
    ) -> list[str]:
        pods: set[str] = set()
        for asset_class in asset_classes or []:
            pods.update(_ASSET_TO_PODS.get(str(asset_class).lower(), ()))
        for factor in factors or []:
            pods.update(_FACTOR_PODS.get(str(factor).lower(), ()))
        symbol_set = {str(s).upper() for s in symbols or []}
        for pod_id, ctx in (pod_contexts or {}).items():
            universe = {str(s).upper() for s in ctx.get("universe", []) or []}
            held = {str(s).upper() for s in ctx.get("held_symbols", []) or []}
            if symbol_set & (universe | held):
                pods.add(pod_id)
        return sorted(p for p in pods if p in POD_IDS)

    @staticmethod
    def _thread_id(event: CatalystEvent) -> str:
        symbols = ",".join(sorted(str(s).upper() for s in event.affected_symbols or [])[:6])
        factors = ",".join(sorted(str(f).lower() for f in event.factors or [])[:6])
        title_words = " ".join(str(event.title or "").lower().split()[:8])
        return "thread:" + _hash_key(symbols, factors, title_words)

    @staticmethod
    def _routing_reason(event: CatalystEvent, pod_contexts: dict[str, dict]) -> dict[str, str]:
        reasons: dict[str, str] = {}
        symbols = {str(s).upper() for s in event.affected_symbols or []}
        factors = ", ".join(event.factors or [])
        for pod in event.affected_pods or []:
            ctx = pod_contexts.get(pod, {}) if isinstance(pod_contexts, dict) else {}
            held = {str(s).upper() for s in ctx.get("held_symbols", []) or []}
            universe = {str(s).upper() for s in ctx.get("universe", []) or []}
            overlap = sorted(symbols & (held | universe))
            if overlap:
                reasons[pod] = f"Symbol overlap: {', '.join(overlap[:5])}"
            elif factors:
                reasons[pod] = f"Factor exposure: {factors}"
            else:
                reasons[pod] = "Macro/risk-sentiment event routed to pod watchlist"
        return reasons

    @staticmethod
    def _transmission_path(event: CatalystEvent) -> str:
        factors = set(str(f).lower() for f in event.factors or [])
        paths: list[str] = []
        if "energy" in factors:
            paths.append("energy prices -> inflation expectations -> rates/USD/risk sentiment")
        if "real_yields" in factors or "rates" in factors:
            paths.append("nominal yields/breakevens -> real yields -> duration, gold, FX, crypto multiples")
        if "geopolitics" in factors:
            paths.append("geopolitical risk -> safe-haven demand, oil risk premium, volatility")
        if "crypto_liquidity" in factors:
            paths.append("liquidity/on-chain activity -> crypto beta and altcoin rotation")
        if "earnings" in factors:
            paths.append("fundamental revisions -> sector/single-name expected return")
        return "; ".join(paths) or "headline/event -> pod-specific repricing risk"

    @staticmethod
    def _uncertainty_note(event: CatalystEvent) -> str:
        direction = str(event.direction or "mixed").lower()
        if direction == "mixed":
            return "Direction is conditional; PM must state which market reaction dominates before trading."
        if "rates" in event.factors or "real_yields" in event.factors:
            return "Watch whether real yields and USD confirm or offset the thesis."
        return "Confirm with live prices, positioning, and thesis invalidation before adding risk."

    def _suggest_specialists(self, factors: list, pods: list) -> list[str]:
        specialists: list[str] = []
        for factor in factors or []:
            specialist = _SPECIALIST_BY_FACTOR.get(str(factor).lower())
            if specialist and specialist not in specialists:
                specialists.append(specialist)
        if "crypto" in pods and "crypto_onchain" not in specialists:
            specialists.append("crypto_onchain")
        if "commodities" in pods and "commodity_supply_demand" not in specialists:
            specialists.append("commodity_supply_demand")
        if "fx" in pods and "fx_rates_policy" not in specialists:
            specialists.append("fx_rates_policy")
        if "equities" in pods and "asset_fundamental" not in specialists:
            specialists.append("asset_fundamental")
        if "risk_skeptic" not in specialists:
            specialists.append("risk_skeptic")
        return specialists[:4]

    @staticmethod
    def _novelty_from_item(item: dict) -> float:
        first_seen = item.get("first_seen_at")
        try:
            if isinstance(first_seen, str):
                dt = datetime.fromisoformat(first_seen.replace("Z", "+00:00"))
                age_hours = max(0.0, (_now() - dt.astimezone(timezone.utc)).total_seconds() / 3600)
                return _clamp(1.0 - min(age_hours / 72.0, 0.85))
        except Exception:
            pass
        return 0.55

    @staticmethod
    def _direction_from_text(text: str, sentiment: Any) -> str:
        try:
            s = float(sentiment)
            if s > 0.20:
                return "bullish"
            if s < -0.20:
                return "bearish"
        except (TypeError, ValueError):
            pass
        t = text.lower()
        if any(word in t for word in ("rally", "beats", "surges", "stronger", "easing", "cuts")):
            return "bullish"
        if any(word in t for word in ("selloff", "misses", "falls", "weak", "hawkish", "war")):
            return "bearish"
        return "mixed"

    @staticmethod
    def _num(value: Any) -> float | None:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _dedupe_events(events: list[CatalystEvent]) -> list[CatalystEvent]:
        seen: set[str] = set()
        out: list[CatalystEvent] = []
        for event in events:
            if event.event_id in seen:
                continue
            seen.add(event.event_id)
            out.append(event)
        return out

    @staticmethod
    def _thread_events(events: list[CatalystEvent]) -> list[CatalystEvent]:
        """Merge repeated event threads enough to reduce dashboard and PM noise."""
        by_thread: dict[str, CatalystEvent] = {}
        for event in events:
            thread_id = event.thread_id or ForesightService._thread_id(event)
            existing = by_thread.get(thread_id)
            if not existing:
                by_thread[thread_id] = event.model_copy(update={"thread_id": thread_id})
                continue
            source_refs = list(existing.source_refs or [])
            seen_refs = {str(ref) for ref in source_refs}
            for ref in event.source_refs or []:
                key = str(ref)
                if key not in seen_refs:
                    source_refs.append(ref)
                    seen_refs.add(key)
            merged_symbols = sorted({*(existing.affected_symbols or []), *(event.affected_symbols or [])})
            merged_pods = sorted({*(existing.affected_pods or []), *(event.affected_pods or [])})
            merged_factors = sorted({*(existing.factors or []), *(event.factors or [])})
            chosen = event if float(event.materiality_score or 0.0) > float(existing.materiality_score or 0.0) else existing
            by_thread[thread_id] = chosen.model_copy(update={
                "thread_id": thread_id,
                "source_refs": source_refs[:12],
                "affected_symbols": merged_symbols,
                "affected_pods": merged_pods,
                "factors": merged_factors,
                "summary": (chosen.summary or "")[:700],
            })
        return sorted(
            by_thread.values(),
            key=lambda e: (float(e.materiality_score or 0.0), float(e.impact_score or 0.0), float(e.confidence or 0.0)),
            reverse=True,
        )
