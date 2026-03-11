from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from src.core.models.polymarket import PolymarketSignal

logger = logging.getLogger(__name__)

NEW_WINDOW = timedelta(hours=6)
RESOLVED_GRACE = timedelta(hours=1)
STALE_UNSEEN = timedelta(hours=24)
STALE_VOLUME_FLOOR = 50_000.0
DEEP_REFRESH_INTERVAL = timedelta(hours=24)
PRICE_HISTORY_CAP = 100


@dataclass
class TrackedMarket:
    market_id: str
    question: str
    first_seen: datetime
    last_seen: datetime
    end_date: datetime | None
    status: str  # "new" | "watching" | "resolved"
    implied_prob: float
    yes_price: float
    no_price: float
    volume_24h: float
    open_interest: float
    spread: float
    tags: list[str]
    prob_at_first_seen: float
    price_history: list[tuple[datetime, float]] = field(default_factory=list)


class MarketTracker:
    """Maintains a rolling watchlist of Polymarket markets with lifecycle tracking.

    Merges fresh signals each cycle, tracks first-seen timestamps, computes
    probability deltas, and prunes stale/expired/resolved markets.
    """

    def __init__(self, max_markets: int = 30) -> None:
        self._max_markets = max_markets
        self._watchlist: dict[str, TrackedMarket] = {}
        self._last_deep_refresh: datetime | None = None

    @property
    def watchlist_size(self) -> int:
        return len(self._watchlist)

    def should_deep_refresh(self) -> bool:
        if self._last_deep_refresh is None:
            return True
        return datetime.now(timezone.utc) - self._last_deep_refresh >= DEEP_REFRESH_INTERVAL

    def mark_deep_refresh_done(self) -> None:
        self._last_deep_refresh = datetime.now(timezone.utc)

    def update(self, fresh_signals: list[PolymarketSignal]) -> list[dict]:
        """Merge fresh signals into watchlist, prune stale entries, return enriched dicts."""
        now = datetime.now(timezone.utc)

        seen_ids: set[str] = set()
        for sig in fresh_signals:
            seen_ids.add(sig.market_id)
            if sig.market_id in self._watchlist:
                self._update_existing(sig, now)
            else:
                self._add_new(sig, now)

        self._prune(now, seen_ids)
        self._enforce_cap()

        return self._to_enriched_dicts(now)

    def _add_new(self, sig: PolymarketSignal, now: datetime) -> None:
        tm = TrackedMarket(
            market_id=sig.market_id,
            question=sig.question,
            first_seen=now,
            last_seen=now,
            end_date=sig.end_date,
            status="new",
            implied_prob=sig.implied_prob,
            yes_price=sig.yes_price,
            no_price=sig.no_price,
            volume_24h=sig.volume_24h,
            open_interest=sig.open_interest,
            spread=sig.spread,
            tags=list(sig.tags),
            prob_at_first_seen=sig.implied_prob,
            price_history=[(now, sig.implied_prob)],
        )
        self._watchlist[sig.market_id] = tm
        logger.debug("MarketTracker: added new market %s", sig.market_id[:12])

    def _update_existing(self, sig: PolymarketSignal, now: datetime) -> None:
        tm = self._watchlist[sig.market_id]
        tm.last_seen = now
        tm.implied_prob = sig.implied_prob
        tm.yes_price = sig.yes_price
        tm.no_price = sig.no_price
        tm.volume_24h = sig.volume_24h
        tm.open_interest = sig.open_interest
        tm.spread = sig.spread
        if sig.end_date is not None:
            tm.end_date = sig.end_date
        if sig.tags:
            tm.tags = list(sig.tags)

        tm.price_history.append((now, sig.implied_prob))
        if len(tm.price_history) > PRICE_HISTORY_CAP:
            tm.price_history = tm.price_history[-PRICE_HISTORY_CAP:]

        if tm.status == "new" and (now - tm.first_seen) >= NEW_WINDOW:
            tm.status = "watching"

        if sig.yes_price >= 0.99 or sig.no_price >= 0.99:
            tm.status = "resolved"

    def _prune(self, now: datetime, seen_ids: set[str]) -> None:
        to_remove: list[str] = []
        for mid, tm in self._watchlist.items():
            if tm.end_date and tm.end_date < now:
                to_remove.append(mid)
                continue
            if tm.status == "resolved" and (now - tm.last_seen) >= RESOLVED_GRACE:
                to_remove.append(mid)
                continue
            unseen_duration = now - tm.last_seen
            if mid not in seen_ids and unseen_duration >= STALE_UNSEEN and tm.volume_24h < STALE_VOLUME_FLOOR:
                to_remove.append(mid)

        for mid in to_remove:
            logger.debug("MarketTracker: pruned market %s", mid[:12])
            del self._watchlist[mid]

    def _enforce_cap(self) -> None:
        if len(self._watchlist) <= self._max_markets:
            return
        ranked = sorted(
            self._watchlist.values(),
            key=lambda tm: tm.volume_24h,
            reverse=True,
        )
        keep_ids = {tm.market_id for tm in ranked[: self._max_markets]}
        self._watchlist = {mid: tm for mid, tm in self._watchlist.items() if mid in keep_ids}

    def _to_enriched_dicts(self, now: datetime) -> list[dict]:
        results: list[dict] = []
        for tm in sorted(self._watchlist.values(), key=lambda t: t.volume_24h, reverse=True):
            if tm.status == "new" and (now - tm.first_seen) >= NEW_WINDOW:
                tm.status = "watching"

            prob_change = round(tm.implied_prob - tm.prob_at_first_seen, 6)
            end_iso = tm.end_date.isoformat() if tm.end_date else None

            d = {
                "market_id": tm.market_id,
                "question": tm.question,
                "yes_price": tm.yes_price,
                "no_price": tm.no_price,
                "implied_prob": tm.implied_prob,
                "spread": tm.spread,
                "volume_24h": tm.volume_24h,
                "open_interest": tm.open_interest,
                "timestamp": now.isoformat(),
                "end_date": end_iso,
                "tags": tm.tags,
                "status": tm.status,
                "first_seen": tm.first_seen.isoformat(),
                "prob_change": prob_change,
            }
            results.append(d)
        return results
