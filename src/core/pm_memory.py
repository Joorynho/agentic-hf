"""Persistent PM decision memory backed by DuckDB."""
from __future__ import annotations
import json
import math
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.bus.audit_log import AuditLog

_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS pm_decisions (
    id          INTEGER,
    pod_id      VARCHAR NOT NULL,
    ts          TIMESTAMP NOT NULL,
    action_summary VARCHAR,
    reasoning   VARCHAR,
    symbols     VARCHAR,
    outcome     VARCHAR DEFAULT 'open'
)
"""

HALF_LIFE_DAYS = 7.0
WINDOW_DAYS    = 30
TOP_N          = 10


class PMMemory:
    def __init__(self, pod_id: str, audit_log: "AuditLog") -> None:
        self._pod_id = pod_id
        self._db = audit_log
        self._db._conn.execute(_TABLE_DDL)

    def record(self, action_summary: str, reasoning: str, symbols: list[str]) -> None:
        self._db._conn.execute(
            "INSERT INTO pm_decisions (pod_id, ts, action_summary, reasoning, symbols, outcome) "
            "VALUES (?, ?, ?, ?, ?, 'open')",
            [self._pod_id, datetime.now(timezone.utc), action_summary[:500],
             reasoning[:1000], json.dumps(symbols)],
        )

    def mark_outcome(self, symbol: str, outcome: str) -> None:
        self._db._conn.execute(
            "UPDATE pm_decisions SET outcome = ? "
            "WHERE pod_id = ? AND outcome = 'open' AND symbols LIKE ?",
            [outcome, self._pod_id, f'%"{symbol}"%'],
        )

    def recall(self) -> str:
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)
        try:
            rows = self._db._conn.execute(
                "SELECT ts, action_summary, reasoning, symbols, outcome "
                "FROM pm_decisions "
                "WHERE pod_id = ? "
                "  AND ts >= ? "
                "ORDER BY ts DESC LIMIT 50",
                [self._pod_id, cutoff],
            ).fetchall()
        except Exception:
            return ""

        if not rows:
            return ""

        now = datetime.now(timezone.utc)
        scored: list[tuple[float, str]] = []
        for row in rows:
            ts, action, reasoning, syms_json, outcome = row
            if hasattr(ts, 'replace'):
                ts_aware = ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts
            else:
                ts_aware = now
            age_days = (now - ts_aware).total_seconds() / 86400
            weight = math.exp(-math.log(2) * age_days / HALF_LIFE_DAYS)
            syms = ", ".join(json.loads(syms_json or "[]"))
            line = f"[{ts_aware.strftime('%Y-%m-%d')}] {action} | symbols={syms} | outcome={outcome} | {(reasoning or '')[:120]}"
            scored.append((weight, line))

        scored.sort(reverse=True)
        top = [line for _, line in scored[:TOP_N]]
        return "PAST DECISIONS (recency-weighted, last 30 days):\n" + "\n".join(top)
