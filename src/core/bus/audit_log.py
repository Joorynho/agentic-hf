from __future__ import annotations
import duckdb, json
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

class AuditLog:
    def __init__(self, db_path: str = ":memory:"):
        self._conn = duckdb.connect(db_path)
        self._conn.execute(CREATE_SQL)

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

    def close(self) -> None:
        self._conn.close()
