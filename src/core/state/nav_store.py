"""
NavStore — SQLite-backed NAV history store.

Stores per-iteration NAV snapshots so performance metrics survive server
restarts. Uses Python's built-in sqlite3 module (zero new dependencies).
"""

import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


class NavStore:
    """Persistent NAV snapshot store backed by a SQLite file."""

    def __init__(self, db_path: str) -> None:
        """Open (or create) the SQLite file and initialise the schema."""
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(str(path))
        self._conn.row_factory = sqlite3.Row
        self._create_schema()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _create_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS nav_snapshots (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                pod_id    TEXT    NOT NULL,
                ts        TEXT    NOT NULL,
                nav       REAL    NOT NULL,
                cash      REAL    NOT NULL,
                invested  REAL    NOT NULL,
                realized  REAL    NOT NULL
            )
            """
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def write_snapshot(
        self,
        pod_id: str,
        nav: float,
        cash: float,
        invested: float,
        realized: float,
        ts: str | None = None,
    ) -> None:
        """Insert a NAV snapshot row for *pod_id* at timestamp *ts*.

        If *ts* is None the current UTC time is used.
        """
        if ts is None:
            ts = datetime.now(timezone.utc).isoformat()

        self._conn.execute(
            """
            INSERT INTO nav_snapshots (pod_id, ts, nav, cash, invested, realized)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (pod_id, ts, nav, cash, invested, realized),
        )
        self._conn.commit()

    def read_history(
        self,
        pod_id: str | None = None,
        limit: int = 200,
    ) -> list[dict]:
        """Return NAV rows sorted ascending by *ts*.

        If *pod_id* is given, only rows for that pod are returned.
        Each row is a plain dict with keys:
        ``pod_id, ts, nav, cash, invested, realized``.
        """
        if pod_id is not None:
            cursor = self._conn.execute(
                """
                SELECT pod_id, ts, nav, cash, invested, realized
                FROM nav_snapshots
                WHERE pod_id = ?
                ORDER BY ts ASC
                LIMIT ?
                """,
                (pod_id, limit),
            )
        else:
            cursor = self._conn.execute(
                """
                SELECT pod_id, ts, nav, cash, invested, realized
                FROM nav_snapshots
                ORDER BY ts ASC
                LIMIT ?
                """,
                (limit,),
            )

        return [dict(row) for row in cursor.fetchall()]

    def read_firm_history(self, limit: int = 200) -> list[dict]:
        """Return firm-level (all-pods-combined) NAV history.

        Rows are grouped by *ts*; nav/cash/invested/realized are summed
        across pods for each timestamp.  The last *limit* unique
        timestamps are returned, sorted ascending by *ts*.
        """
        # Fetch all rows ordered ascending so the grouping is stable.
        cursor = self._conn.execute(
            """
            SELECT ts, nav, cash, invested, realized
            FROM nav_snapshots
            ORDER BY ts ASC
            """
        )
        rows = cursor.fetchall()

        # Aggregate into ordered dict keyed by ts.
        agg: dict[str, dict] = {}
        for row in rows:
            ts = row["ts"]
            if ts not in agg:
                agg[ts] = {"ts": ts, "nav": 0.0, "cash": 0.0, "invested": 0.0, "realized": 0.0}
            agg[ts]["nav"] += row["nav"]
            agg[ts]["cash"] += row["cash"]
            agg[ts]["invested"] += row["invested"]
            agg[ts]["realized"] += row["realized"]

        # Apply limit to the last N unique timestamps.
        unique_ts = list(agg.keys())
        if len(unique_ts) > limit:
            unique_ts = unique_ts[-limit:]

        return [agg[ts] for ts in unique_ts]

    def close(self) -> None:
        """Close the SQLite connection.

        Must be called before process exit on Windows to release the
        file lock.
        """
        try:
            self._conn.close()
        except Exception:
            pass
