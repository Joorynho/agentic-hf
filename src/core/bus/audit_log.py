from __future__ import annotations
import duckdb, json
from datetime import datetime, timezone
from ..models.messages import AgentMessage

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS messages (
    id VARCHAR PRIMARY KEY,
    timestamp TIMESTAMP,
    sender VARCHAR,
    recipient VARCHAR,
    topic VARCHAR,
    payload JSON,
    correlation_id VARCHAR
)
"""

KV_STORE_SQL = """
CREATE TABLE IF NOT EXISTS kv_store (
    key VARCHAR PRIMARY KEY,
    value JSON,
    updated_at TIMESTAMP
)
"""

class AuditLog:
    def __init__(self, db_path: str = ":memory:"):
        self._conn = duckdb.connect(db_path)
        self._db_path = db_path
        self._conn.execute(CREATE_SQL)
        self._conn.execute(KV_STORE_SQL)

    def record(self, message: AgentMessage) -> None:
        self._conn.execute(
            "INSERT INTO messages VALUES (?,?,?,?,?,?,?)",
            [str(message.id), message.timestamp, message.sender,
             message.recipient, message.topic,
             json.dumps(message.payload), str(message.correlation_id)]
        )

    def query(self, sql: str) -> list[dict]:
        result = self._conn.execute(sql).fetchall()
        cols = [d[0] for d in self._conn.description]
        return [dict(zip(cols, row)) for row in result]

    def kv_set(self, key: str, value) -> None:
        """Store a key-value pair (upsert)."""
        now = datetime.now(timezone.utc)
        self._conn.execute(
            "INSERT OR REPLACE INTO kv_store VALUES (?, ?, ?)",
            [key, json.dumps(value), now],
        )

    def kv_get(self, key: str, default=None):
        """Retrieve a value by key, returning default if not found."""
        try:
            result = self._conn.execute(
                "SELECT value FROM kv_store WHERE key = ?", [key]
            ).fetchone()
            if result:
                return json.loads(result[0])
        except Exception:
            pass
        return default

    def close(self) -> None:
        self._conn.close()
