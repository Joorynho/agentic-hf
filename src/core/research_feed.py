from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import duckdb


_ITEM_SCHEMA = """
CREATE TABLE IF NOT EXISTS research_feed_items (
    item_key VARCHAR PRIMARY KEY,
    first_seen_at TIMESTAMP,
    last_seen_at TIMESTAMP,
    published_at TIMESTAMP,
    source VARCHAR,
    source_type VARCHAR,
    title VARCHAR,
    text VARCHAR,
    url VARCHAR,
    category VARCHAR,
    sentiment DOUBLE,
    reliability DOUBLE,
    asset_classes JSON,
    factors JSON,
    tickers JSON,
    urgency DOUBLE,
    raw JSON
)
"""

_SOURCE_SCHEMA = """
CREATE TABLE IF NOT EXISTS research_source_health (
    source VARCHAR PRIMARY KEY,
    source_type VARCHAR,
    last_fetch_at TIMESTAMP,
    last_success_at TIMESTAMP,
    status VARCHAR,
    item_count INTEGER,
    consecutive_failures INTEGER,
    error VARCHAR
)
"""

_CATALYST_SCHEMA = """
CREATE TABLE IF NOT EXISTS catalyst_events (
    event_id VARCHAR PRIMARY KEY,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    title VARCHAR,
    summary VARCHAR,
    source_refs JSON,
    novelty_score DOUBLE,
    impact_score DOUBLE,
    confidence DOUBLE,
    affected_pods JSON,
    affected_symbols JSON,
    factors JSON,
    direction VARCHAR,
    horizon VARCHAR,
    suggested_specialists JSON,
    status VARCHAR,
    raw JSON
)
"""

_CATALYST_V2_COLUMNS: dict[str, str] = {
    "thread_id": "VARCHAR",
    "materiality_score": "DOUBLE",
    "horizon_start": "TIMESTAMP",
    "horizon_end": "TIMESTAMP",
    "transmission_path": "VARCHAR",
    "uncertainty": "VARCHAR",
    "routing_reason": "JSON",
    "linked_run_ids": "JSON",
    "linked_report_ids": "JSON",
    "linked_trade_ids": "JSON",
    "outcome_score": "DOUBLE",
    "hindsight_score": "DOUBLE",
    "reviewed_at": "TIMESTAMP",
}

_ASSET_KEYWORDS: dict[str, tuple[str, ...]] = {
    "equities": (
        "stock", "stocks", "equity", "equities", "earnings", "shares", "nasdaq",
        "s&p", "spx", "dow", "sector", "tech", "bank", "banks", "credit",
    ),
    "fx": (
        "dollar", "usd", "euro", "eur", "yen", "jpy", "sterling", "pound",
        "currency", "currencies", "forex", "fx", "exchange rate", "dxy",
    ),
    "crypto": (
        "crypto", "bitcoin", "btc", "ether", "ethereum", "eth", "solana",
        "sol", "xrp", "stablecoin", "token", "blockchain", "coinbase",
    ),
    "commodities": (
        "oil", "crude", "brent", "wti", "opec", "gas", "lng", "gold",
        "silver", "copper", "metal", "metals", "wheat", "corn", "soybean",
        "commodity", "commodities", "hormuz", "energy",
    ),
}

_FACTOR_KEYWORDS: dict[str, tuple[str, ...]] = {
    "inflation": ("inflation", "cpi", "ppi", "prices", "breakeven", "wages"),
    "rates": ("fed", "fomc", "rate", "rates", "yield", "treasury", "ecb", "boe", "boj"),
    "real_yields": ("real yield", "tips", "inflation-adjusted", "breakeven"),
    "usd": ("dollar", "usd", "dxy", "greenback"),
    "energy": ("oil", "crude", "brent", "wti", "gas", "lng", "opec", "hormuz"),
    "metals": ("gold", "silver", "copper", "precious metals", "miner"),
    "geopolitics": ("war", "conflict", "sanction", "tariff", "hormuz", "iran", "china", "geopolitic"),
    "risk_sentiment": ("risk-off", "risk on", "volatility", "vix", "selloff", "rally"),
    "credit": ("credit", "spread", "default", "bankruptcy", "high yield"),
    "crypto_liquidity": ("etf", "stablecoin", "staking", "exchange", "wallet", "defi"),
    "earnings": ("earnings", "revenue", "profit", "guidance", "margin"),
}

_TICKER_ALIASES: dict[str, tuple[str, ...]] = {
    "SPY": ("spy", "s&p", "s&p 500", "spx"),
    "QQQ": ("qqq", "nasdaq", "nasdaq 100"),
    "TLT": ("tlt", "long bond", "20-year treasury", "treasury bond"),
    "GLD": ("gld", "gold", "bullion"),
    "SLV": ("slv", "silver"),
    "GDX": ("gdx", "gold miners", "miners"),
    "GDXJ": ("gdxj", "junior miners"),
    "USO": ("uso", "wti", "crude oil", "oil"),
    "UNG": ("ung", "natural gas", "nat gas", "lng"),
    "UUP": ("uup", "dollar index", "dxy"),
    "USDU": ("usdu", "dollar", "usd"),
    "FXE": ("fxe", "euro", "eur"),
    "FXY": ("fxy", "yen", "jpy"),
    "BTC/USD": ("btc", "bitcoin"),
    "ETH/USD": ("eth", "ether", "ethereum"),
    "SOL/USD": ("sol", "solana"),
    "XRP/USD": ("xrp", "ripple"),
    "XLE": ("xle", "energy sector"),
    "XLF": ("xlf", "financials", "banks"),
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return _utc_now()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, default=str, sort_keys=True)


def _json_loads(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _item_text(item: dict[str, Any]) -> str:
    return str(
        item.get("text")
        or item.get("title")
        or item.get("headline")
        or item.get("summary")
        or item.get("body_snippet")
        or ""
    ).strip()


def _item_source(item: dict[str, Any]) -> str:
    return str(
        item.get("handle")
        or item.get("username")
        or item.get("source")
        or item.get("publisher")
        or "news"
    ).strip() or "news"


def _item_title(item: dict[str, Any]) -> str:
    return str(item.get("title") or item.get("headline") or _item_text(item)).strip()


def _item_key(item: dict[str, Any]) -> str:
    explicit = str(item.get("dedupe_hash") or item.get("id") or "").strip()
    if explicit:
        return explicit
    url = str(item.get("url") or "").strip().lower()
    if url and url != "#":
        return hashlib.sha256(url.encode()).hexdigest()[:24]
    payload = f"{_item_source(item).lower()}|{_item_text(item).lower()[:240]}"
    return hashlib.sha256(payload.encode()).hexdigest()[:24]


def classify_research_item(item: dict[str, Any]) -> dict[str, Any]:
    text = f"{_item_title(item)} {_item_text(item)} {item.get('category', '')}".lower()
    category = str(item.get("category") or "").lower()

    asset_classes = set()
    for asset_class, keywords in _ASSET_KEYWORDS.items():
        if asset_class in category or any(keyword in text for keyword in keywords):
            asset_classes.add(asset_class)
    if not asset_classes:
        asset_classes.add("macro")

    factors = {
        factor
        for factor, keywords in _FACTOR_KEYWORDS.items()
        if any(keyword in text for keyword in keywords)
    }

    tickers = set()
    raw_entities = item.get("entities") or []
    if isinstance(raw_entities, list):
        tickers.update(str(entity).upper() for entity in raw_entities if entity)
    for ticker, aliases in _TICKER_ALIASES.items():
        if any(alias in text for alias in aliases):
            tickers.add(ticker)

    urgency = 0.20
    urgency += min(len(asset_classes) - 1, 2) * 0.10
    urgency += min(len(factors), 4) * 0.08
    urgency += 0.18 if tickers else 0.0
    urgency += 0.16 if any(f in factors for f in ("geopolitics", "rates", "energy", "real_yields")) else 0.0
    try:
        urgency += min(abs(float(item.get("sentiment") or 0.0)), 1.0) * 0.12
    except (TypeError, ValueError):
        pass
    urgency = max(0.0, min(1.0, urgency))

    return {
        "asset_classes": sorted(asset_classes),
        "factors": sorted(factors),
        "tickers": sorted(tickers),
        "urgency": round(urgency, 4),
    }


class ResearchFeedStore:
    """DuckDB-backed research-feed persistence and source-health tracking."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self._db_path = db_path
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(db_path)
        self._conn.execute(_ITEM_SCHEMA)
        self._conn.execute(_SOURCE_SCHEMA)
        self._conn.execute(_CATALYST_SCHEMA)
        self._migrate_catalyst_schema()

    def close(self) -> None:
        self._conn.close()

    def _migrate_catalyst_schema(self) -> None:
        """Add V2 Catalyst Ledger columns without disturbing existing stores."""
        try:
            rows = self._conn.execute("PRAGMA table_info('catalyst_events')").fetchall()
            existing = {str(row[1]) for row in rows}
            for column, column_type in _CATALYST_V2_COLUMNS.items():
                if column not in existing:
                    self._conn.execute(f"ALTER TABLE catalyst_events ADD COLUMN {column} {column_type}")
        except Exception:
            # Old rows still carry the full event JSON in `raw`; callers can degrade
            # gracefully if the migration is unavailable.
            pass

    def record_source_status(
        self,
        source: str,
        source_type: str,
        status: str,
        item_count: int = 0,
        error: str = "",
        ts: datetime | None = None,
    ) -> None:
        ts = ts or _utc_now()
        source = source or source_type or "unknown"
        previous = self._conn.execute(
            "SELECT consecutive_failures, last_success_at FROM research_source_health WHERE source = ?",
            [source],
        ).fetchone()
        previous_failures = int(previous[0] or 0) if previous else 0
        previous_success = previous[1] if previous else None
        is_ok = status.lower() in {"ok", "cached", "success"}
        failures = 0 if is_ok else previous_failures + 1
        last_success = ts if is_ok else previous_success
        self._conn.execute(
            """
            INSERT OR REPLACE INTO research_source_health
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [source, source_type, ts, last_success, status, int(item_count), failures, error[:500]],
        )

    def record_items(
        self,
        items: Iterable[dict[str, Any]],
        source_type: str,
        ts: datetime | None = None,
    ) -> int:
        ts = ts or _utc_now()
        count = 0
        per_source: dict[str, int] = {}
        for raw in items or []:
            if hasattr(raw, "model_dump"):
                item = raw.model_dump(mode="json")
            elif isinstance(raw, dict):
                item = dict(raw)
            else:
                continue
            text = _item_text(item)
            title = _item_title(item)
            if not text and not title:
                continue

            source = _item_source(item)
            published_at = _parse_dt(
                item.get("timestamp") or item.get("published") or item.get("published_at") or item.get("date")
            )
            routing = classify_research_item(item)
            item_key = _item_key(item)
            existing = self._conn.execute(
                "SELECT first_seen_at FROM research_feed_items WHERE item_key = ?",
                [item_key],
            ).fetchone()
            first_seen = existing[0] if existing else ts
            sentiment = item.get("sentiment")
            reliability = item.get("reliability_score", item.get("reliability"))
            self._conn.execute(
                """
                INSERT OR REPLACE INTO research_feed_items
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    item_key,
                    first_seen,
                    ts,
                    published_at,
                    source,
                    source_type,
                    title[:500],
                    text[:1200],
                    str(item.get("url") or ""),
                    str(item.get("category") or ""),
                    float(sentiment) if sentiment is not None else None,
                    float(reliability) if reliability is not None else None,
                    _json_dumps(routing["asset_classes"]),
                    _json_dumps(routing["factors"]),
                    _json_dumps(routing["tickers"]),
                    float(routing["urgency"]),
                    _json_dumps(item),
                ],
            )
            count += 1
            per_source[source] = per_source.get(source, 0) + 1

        for source, source_count in per_source.items():
            self.record_source_status(source, source_type, "ok", source_count, ts=ts)
        return count

    def get_items(self, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit or 100), 500))
        rows = self._conn.execute(
            """
            SELECT item_key, first_seen_at, last_seen_at, published_at, source, source_type,
                   title, text, url, category, sentiment, reliability,
                   asset_classes, factors, tickers, urgency, raw
            FROM research_feed_items
            ORDER BY published_at DESC, last_seen_at DESC
            LIMIT ?
            """,
            [limit],
        ).fetchall()
        cols = [d[0] for d in self._conn.description]
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(zip(cols, row))
            for key in ("first_seen_at", "last_seen_at", "published_at"):
                if hasattr(item.get(key), "isoformat"):
                    item[key] = item[key].isoformat()
            item["asset_classes"] = _json_loads(item.get("asset_classes"), [])
            item["factors"] = _json_loads(item.get("factors"), [])
            item["tickers"] = _json_loads(item.get("tickers"), [])
            item["raw"] = _json_loads(item.get("raw"), {})
            result.append(item)
        return result

    def get_source_health(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT source, source_type, last_fetch_at, last_success_at, status,
                   item_count, consecutive_failures, error
            FROM research_source_health
            ORDER BY last_fetch_at DESC
            LIMIT ?
            """,
            [max(1, min(int(limit or 100), 500))],
        ).fetchall()
        cols = [d[0] for d in self._conn.description]
        result = []
        for row in rows:
            item = dict(zip(cols, row))
            for key in ("last_fetch_at", "last_success_at"):
                if hasattr(item.get(key), "isoformat"):
                    item[key] = item[key].isoformat()
            result.append(item)
        return result

    def record_catalyst_events(self, events: Iterable[dict[str, Any]], ts: datetime | None = None) -> int:
        """Persist advisory Foresight catalyst events."""
        ts = ts or _utc_now()
        count = 0
        for raw_event in events or []:
            if hasattr(raw_event, "model_dump"):
                event = raw_event.model_dump(mode="json")
            elif isinstance(raw_event, dict):
                event = dict(raw_event)
            else:
                continue
            event_id = str(event.get("event_id") or "").strip()
            title = str(event.get("title") or "").strip()
            if not event_id or not title:
                continue
            created_at = _parse_dt(event.get("created_at") or ts)
            horizon_start = _parse_dt(event.get("horizon_start")) if event.get("horizon_start") else None
            horizon_end = _parse_dt(event.get("horizon_end")) if event.get("horizon_end") else None
            reviewed_at = _parse_dt(event.get("reviewed_at")) if event.get("reviewed_at") else None
            self._conn.execute(
                """
                INSERT OR REPLACE INTO catalyst_events (
                    event_id, created_at, updated_at, title, summary, source_refs,
                    novelty_score, impact_score, confidence, affected_pods,
                    affected_symbols, factors, direction, horizon,
                    suggested_specialists, status, raw, thread_id,
                    materiality_score, horizon_start, horizon_end, transmission_path,
                    uncertainty, routing_reason, linked_run_ids, linked_report_ids,
                    linked_trade_ids, outcome_score, hindsight_score, reviewed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    event_id,
                    created_at,
                    ts,
                    title[:500],
                    str(event.get("summary") or "")[:1400],
                    _json_dumps(event.get("source_refs") or []),
                    float(event.get("novelty_score") or 0.0),
                    float(event.get("impact_score") or 0.0),
                    float(event.get("confidence") or 0.0),
                    _json_dumps(event.get("affected_pods") or []),
                    _json_dumps(event.get("affected_symbols") or []),
                    _json_dumps(event.get("factors") or []),
                    str(event.get("direction") or "mixed"),
                    str(event.get("horizon") or "days"),
                    _json_dumps(event.get("suggested_specialists") or []),
                    str(event.get("status") or "active"),
                    _json_dumps(event),
                    str(event.get("thread_id") or event_id),
                    float(event.get("materiality_score") or event.get("impact_score") or 0.0),
                    horizon_start,
                    horizon_end,
                    str(event.get("transmission_path") or ""),
                    str(event.get("uncertainty") or ""),
                    _json_dumps(event.get("routing_reason") or {}),
                    _json_dumps(event.get("linked_run_ids") or []),
                    _json_dumps(event.get("linked_report_ids") or []),
                    _json_dumps(event.get("linked_trade_ids") or []),
                    float(event.get("outcome_score")) if event.get("outcome_score") is not None else None,
                    float(event.get("hindsight_score")) if event.get("hindsight_score") is not None else None,
                    reviewed_at,
                ],
            )
            count += 1
        return count

    def get_catalyst_events(self, limit: int = 100, pod_id: str | None = None) -> list[dict[str, Any]]:
        """Return persisted Catalyst Ledger events, optionally filtered by pod."""
        limit = max(1, min(int(limit or 100), 500))
        rows = self._conn.execute(
            """
            SELECT event_id, created_at, updated_at, title, summary, source_refs,
                   novelty_score, impact_score, confidence, affected_pods,
                   affected_symbols, factors, direction, horizon,
                   suggested_specialists, status, raw, thread_id,
                   materiality_score, horizon_start, horizon_end, transmission_path,
                   uncertainty, routing_reason, linked_run_ids, linked_report_ids,
                   linked_trade_ids, outcome_score, hindsight_score, reviewed_at
            FROM catalyst_events
            ORDER BY materiality_score DESC, impact_score DESC, confidence DESC, updated_at DESC
            LIMIT ?
            """,
            [limit],
        ).fetchall()
        cols = [d[0] for d in self._conn.description]
        result: list[dict[str, Any]] = []
        pod_filter = (pod_id or "").strip().lower()
        for row in rows:
            item = dict(zip(cols, row))
            for key in ("created_at", "updated_at", "horizon_start", "horizon_end", "reviewed_at"):
                if hasattr(item.get(key), "isoformat"):
                    item[key] = item[key].isoformat()
            for key in (
                "source_refs", "affected_pods", "affected_symbols", "factors",
                "suggested_specialists", "linked_run_ids", "linked_report_ids",
                "linked_trade_ids",
            ):
                item[key] = _json_loads(item.get(key), [])
            item["routing_reason"] = _json_loads(item.get("routing_reason"), {})
            item["raw"] = _json_loads(item.get("raw"), {})
            for key, value in item.get("raw", {}).items():
                item.setdefault(key, value)
            if pod_filter and pod_filter not in [str(p).lower() for p in item.get("affected_pods", [])]:
                continue
            result.append(item)
        return result

    def catalyst_threads(self, limit: int = 100, pod_id: str | None = None) -> list[dict[str, Any]]:
        events = self.get_catalyst_events(limit=max(limit * 4, 100), pod_id=pod_id)
        threads: dict[str, dict[str, Any]] = {}
        for event in events:
            thread_id = str(event.get("thread_id") or event.get("event_id") or "")
            if not thread_id:
                continue
            thread = threads.setdefault(thread_id, {
                "thread_id": thread_id,
                "title": event.get("title", ""),
                "status": event.get("status", "active"),
                "events": [],
                "event_count": 0,
                "affected_pods": set(),
                "affected_symbols": set(),
                "factors": set(),
                "materiality_score": 0.0,
                "latest_updated_at": "",
                "hindsight_score": None,
            })
            thread["events"].append(event)
            thread["event_count"] += 1
            thread["materiality_score"] = max(
                float(thread.get("materiality_score") or 0.0),
                float(event.get("materiality_score") or event.get("impact_score") or 0.0),
            )
            if event.get("updated_at") and str(event.get("updated_at")) > str(thread.get("latest_updated_at") or ""):
                thread["latest_updated_at"] = event.get("updated_at")
                thread["title"] = event.get("title") or thread["title"]
                thread["status"] = event.get("status") or thread["status"]
            for pod in event.get("affected_pods") or []:
                thread["affected_pods"].add(str(pod))
            for symbol in event.get("affected_symbols") or []:
                thread["affected_symbols"].add(str(symbol))
            for factor in event.get("factors") or []:
                thread["factors"].add(str(factor))
            if event.get("hindsight_score") is not None:
                thread["hindsight_score"] = event.get("hindsight_score")
        rows = []
        for thread in threads.values():
            thread["affected_pods"] = sorted(thread["affected_pods"])
            thread["affected_symbols"] = sorted(thread["affected_symbols"])
            thread["factors"] = sorted(thread["factors"])
            thread["events"] = sorted(thread["events"], key=lambda e: e.get("updated_at") or "", reverse=True)[:10]
            rows.append(thread)
        rows.sort(key=lambda t: (float(t.get("materiality_score") or 0.0), t.get("latest_updated_at") or ""), reverse=True)
        return rows[: max(1, min(int(limit or 100), 500))]

    def update_catalyst_lifecycle(
        self,
        event_id: str,
        *,
        status: str | None = None,
        linked_run_ids: list[str] | None = None,
        linked_report_ids: list[str] | None = None,
        linked_trade_ids: list[str] | None = None,
        outcome_score: float | None = None,
        hindsight_score: float | None = None,
        reviewed_at: datetime | None = None,
    ) -> None:
        current = self._conn.execute(
            """
            SELECT linked_run_ids, linked_report_ids, linked_trade_ids, raw
            FROM catalyst_events WHERE event_id=?
            """,
            [event_id],
        ).fetchone()
        if not current:
            return
        existing_runs = _json_loads(current[0], [])
        existing_reports = _json_loads(current[1], [])
        existing_trades = _json_loads(current[2], [])
        raw = _json_loads(current[3], {})

        def merged(existing: list, incoming: list[str] | None) -> list:
            out = [str(x) for x in existing or [] if x]
            for item in incoming or []:
                item = str(item)
                if item and item not in out:
                    out.append(item)
            return out

        runs = merged(existing_runs, linked_run_ids)
        reports = merged(existing_reports, linked_report_ids)
        trades = merged(existing_trades, linked_trade_ids)
        if status:
            raw["status"] = status
        raw["linked_run_ids"] = runs
        raw["linked_report_ids"] = reports
        raw["linked_trade_ids"] = trades
        if outcome_score is not None:
            raw["outcome_score"] = outcome_score
        if hindsight_score is not None:
            raw["hindsight_score"] = hindsight_score
        if reviewed_at is not None:
            raw["reviewed_at"] = reviewed_at.isoformat()
        self._conn.execute(
            """
            UPDATE catalyst_events
            SET status=COALESCE(?, status), updated_at=?, linked_run_ids=?,
                linked_report_ids=?, linked_trade_ids=?, outcome_score=COALESCE(?, outcome_score),
                hindsight_score=COALESCE(?, hindsight_score), reviewed_at=COALESCE(?, reviewed_at),
                raw=?
            WHERE event_id=?
            """,
            [
                status,
                _utc_now(),
                _json_dumps(runs),
                _json_dumps(reports),
                _json_dumps(trades),
                outcome_score,
                hindsight_score,
                reviewed_at,
                _json_dumps(raw),
                event_id,
            ],
        )

    def summary(self, limit: int = 100) -> dict[str, Any]:
        items = self.get_items(limit=limit)
        sources = self.get_source_health()
        return {
            "items": items,
            "sources": sources,
            "catalyst_events": self.get_catalyst_events(limit=limit),
            "item_count": len(items),
            "source_count": len(sources),
            "generated_at": _utc_now().isoformat(),
        }
