"""
NavStore — SQLite-backed NAV history store.

Stores per-iteration NAV snapshots so performance metrics survive server
restarts. Uses Python's built-in sqlite3 module (zero new dependencies).
"""

import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


_COLLAPSE_RATIO = 0.50
_PLACEHOLDER_INVESTED_MAX = 1.0
_PLACEHOLDER_REALIZED_MAX = 1.0
_SEED_REFERENCE_MIN_NAV = 500.0
_SEED_BASELINE_STEP = 100.0
_SEED_BASELINE_TOLERANCE = 0.10


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
        self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_nav_snapshots_ts
            ON nav_snapshots (ts)
            """
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @staticmethod
    def _is_all_cash_placeholder(row: dict, reference_nav: float | None = None) -> bool:
        nav = float(row.get("nav") or 0.0)
        cash = float(row.get("cash") or 0.0)
        invested = abs(float(row.get("invested") or 0.0))
        realized = abs(float(row.get("realized") or 0.0))
        cash_matches_nav = abs(cash - nav) <= max(1.0, nav * 0.02)
        if reference_nav is not None and reference_nav > 0:
            cash_matches_nav = abs(cash - nav) <= max(1.0, reference_nav * 0.02)
        return (
            nav > 0
            and invested <= _PLACEHOLDER_INVESTED_MAX
            and realized <= _PLACEHOLDER_REALIZED_MAX
            and cash_matches_nav
        )

    @staticmethod
    def _infer_seed_baseline(reference_nav: float) -> float:
        """Infer the intended starting allocation from the first valid NAV.

        Historical bugs wrote all-cash seed rows around $100 before the pod was
        actually funded around $1000. If the first valid NAV is slightly away
        from the mandate because prices moved before the first clean snapshot,
        round it back to the nearest clean allocation step.
        """
        if reference_nav <= 0:
            return reference_nav
        rounded = round(reference_nav / _SEED_BASELINE_STEP) * _SEED_BASELINE_STEP
        if rounded >= _SEED_REFERENCE_MIN_NAV:
            tolerance = max(25.0, rounded * _SEED_BASELINE_TOLERANCE)
            if abs(reference_nav - rounded) <= tolerance:
                return rounded
        return reference_nav

    @classmethod
    def _repair_leading_seed_placeholders(cls, rows: list[dict]) -> list[dict]:
        """Repair low all-cash rows written before the real pod allocation.

        This handles the inverse of a restart collapse: when the bad $100 rows
        are at the *start* of the history, there is no previous valid row to
        freeze against. We infer the later funded baseline and rebase only the
        leading all-cash placeholder rows.
        """
        rows_by_pod: dict[str, list[dict]] = defaultdict(list)
        for row in rows:
            rows_by_pod[row.get("pod_id", "")].append(row)

        repaired: list[dict] = []
        for pod_id, pod_rows in rows_by_pod.items():
            pod_rows = sorted(pod_rows, key=lambda r: (r.get("ts", ""), r.get("id", 0)))
            max_nav = max((float(r.get("nav") or 0.0) for r in pod_rows), default=0.0)
            if max_nav < _SEED_REFERENCE_MIN_NAV:
                repaired.extend(pod_rows)
                continue

            valid_threshold = max(_SEED_REFERENCE_MIN_NAV, max_nav * _COLLAPSE_RATIO)
            first_valid = next(
                (r for r in pod_rows if float(r.get("nav") or 0.0) >= valid_threshold),
                None,
            )
            if not first_valid:
                repaired.extend(pod_rows)
                continue

            baseline = cls._infer_seed_baseline(float(first_valid.get("nav") or 0.0))
            for row in pod_rows:
                nav = float(row.get("nav") or 0.0)
                if row is first_valid:
                    repaired.append(row)
                    continue
                if nav >= valid_threshold:
                    repaired.append(row)
                    continue
                if row.get("ts", "") < first_valid.get("ts", "") and cls._is_all_cash_placeholder(row):
                    fixed = dict(row)
                    fixed["nav"] = baseline
                    fixed["cash"] = baseline
                    fixed["invested"] = 0.0
                    fixed["realized"] = 0.0
                    fixed["quality"] = "rebased_seed_placeholder"
                    repaired.append(fixed)
                else:
                    repaired.append(row)

        return sorted(repaired, key=lambda r: (r.get("ts", ""), r.get("id", 0)))

    @staticmethod
    def _looks_like_collapsed_placeholder(row: dict, previous: dict | None) -> bool:
        """Return True when a row looks like a restart/default-capital artifact.

        Real losses usually still have invested capital, realized P&L, or both.
        The bad restart rows we saw were all-cash placeholders around $100 after
        a healthy ~$1000 pod NAV, so freeze those rows at the previous valid NAV.
        """
        if not previous:
            return False
        prev_nav = float(previous.get("nav") or 0.0)
        nav = float(row.get("nav") or 0.0)
        if prev_nav <= 0 or nav < 0:
            return False
        if nav >= prev_nav * _COLLAPSE_RATIO:
            return False
        return NavStore._is_all_cash_placeholder(row, reference_nav=prev_nav)

    @classmethod
    def _freeze_row_at_previous(cls, row: dict, previous: dict) -> dict:
        frozen = dict(row)
        for key in ("nav", "cash", "invested", "realized"):
            frozen[key] = float(previous.get(key) or 0.0)
        frozen["quality"] = "flattened_placeholder"
        return frozen

    @classmethod
    def _repair_rows(cls, rows: list[dict]) -> list[dict]:
        """Flatten implausible placeholder drops within each pod series."""
        rows = cls._repair_leading_seed_placeholders(rows)
        previous_by_pod: dict[str, dict] = {}
        repaired: list[dict] = []
        for row in sorted(rows, key=lambda r: (r.get("ts", ""), r.get("id", 0))):
            pod_id = row.get("pod_id", "")
            previous = previous_by_pod.get(pod_id)
            if cls._looks_like_collapsed_placeholder(row, previous):
                row = cls._freeze_row_at_previous(row, previous)
            else:
                row = dict(row)
                row.setdefault("quality", "ok")
            previous_by_pod[pod_id] = row
            repaired.append(row)
        return repaired

    def _latest_repaired_row(self, pod_id: str) -> dict | None:
        cursor = self._conn.execute(
            """
            SELECT id, pod_id, ts, nav, cash, invested, realized
            FROM nav_snapshots
            WHERE pod_id = ?
            ORDER BY ts ASC, id ASC
            """,
            (pod_id,),
        )
        rows = self._repair_rows([dict(row) for row in cursor.fetchall()])
        return rows[-1] if rows else None

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

        row = {
            "pod_id": pod_id,
            "ts": ts,
            "nav": float(nav),
            "cash": float(cash),
            "invested": float(invested),
            "realized": float(realized),
        }
        previous = self._latest_repaired_row(pod_id)
        if self._looks_like_collapsed_placeholder(row, previous):
            row = self._freeze_row_at_previous(row, previous)

        self._conn.execute(
            """
            INSERT INTO nav_snapshots (pod_id, ts, nav, cash, invested, realized)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                row["pod_id"],
                row["ts"],
                row["nav"],
                row["cash"],
                row["invested"],
                row["realized"],
            ),
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
                FROM (
                    SELECT pod_id, ts, nav, cash, invested, realized
                    FROM nav_snapshots
                    WHERE pod_id = ?
                    ORDER BY ts DESC, id DESC
                    LIMIT ?
                )
                ORDER BY ts ASC
                """,
                (pod_id, limit),
            )
        else:
            cursor = self._conn.execute(
                """
                SELECT pod_id, ts, nav, cash, invested, realized
                FROM (
                    SELECT pod_id, ts, nav, cash, invested, realized
                    FROM nav_snapshots
                    ORDER BY ts DESC, id DESC
                    LIMIT ?
                )
                ORDER BY ts ASC
                """,
                (limit,),
            )

        return self._repair_rows([dict(row) for row in cursor.fetchall()])

    def read_firm_history(self, limit: int = 200) -> list[dict]:
        """Return firm-level (all-pods-combined) NAV history.

        Rows are grouped by *ts*; nav/cash/invested/realized are summed
        across pods for each timestamp.  The last *limit* unique
        timestamps are returned, sorted ascending by *ts*.
        """
        cursor = self._conn.execute(
            """
            SELECT pod_id, ts, nav, cash, invested, realized
            FROM nav_snapshots
            WHERE ts IN (
                SELECT ts
                FROM (
                    SELECT DISTINCT ts
                    FROM nav_snapshots
                    ORDER BY ts DESC
                    LIMIT ?
                )
            )
            ORDER BY ts ASC
            """,
            (limit,),
        )
        rows = self._repair_rows([dict(row) for row in cursor.fetchall()])

        # Aggregate into ordered dict keyed by ts.
        agg: dict[str, dict] = {}
        for row in rows:
            ts = row["ts"]
            if ts not in agg:
                agg[ts] = {
                    "ts": ts,
                    "nav": 0.0,
                    "cash": 0.0,
                    "invested": 0.0,
                    "realized": 0.0,
                    "pods": {},
                }
            agg[ts]["nav"] += row["nav"]
            agg[ts]["cash"] += row["cash"]
            agg[ts]["invested"] += row["invested"]
            agg[ts]["realized"] += row["realized"]
            agg[ts]["pods"][row["pod_id"]] = row["nav"]

        # Apply limit to the last N unique timestamps.
        unique_ts = list(agg.keys())
        if len(unique_ts) > limit:
            unique_ts = unique_ts[-limit:]

        return [agg[ts] for ts in unique_ts]

    def health_summary(self) -> dict:
        """Return diagnostics about persisted NAV history quality."""
        cursor = self._conn.execute(
            """
            SELECT id, pod_id, ts, nav, cash, invested, realized
            FROM nav_snapshots
            ORDER BY ts ASC, id ASC
            """
        )
        raw_rows = [dict(row) for row in cursor.fetchall()]
        repaired_rows = self._repair_rows(raw_rows)
        repaired_by_id = {row.get("id"): row for row in repaired_rows if row.get("id") is not None}
        repaired_count = 0
        quality_counts: dict[str, int] = defaultdict(int)
        latest_by_pod: dict[str, dict] = {}
        first_ts = None
        last_ts = None

        for raw in raw_rows:
            repaired = repaired_by_id.get(raw.get("id"), raw)
            quality = repaired.get("quality", "ok")
            quality_counts[quality] += 1
            if any(
                float(repaired.get(key) or 0.0) != float(raw.get(key) or 0.0)
                for key in ("nav", "cash", "invested", "realized")
            ):
                repaired_count += 1
            ts = repaired.get("ts", "")
            if ts:
                first_ts = ts if first_ts is None or ts < first_ts else first_ts
                last_ts = ts if last_ts is None or ts > last_ts else last_ts
            pod_id = repaired.get("pod_id", "")
            if pod_id:
                latest = latest_by_pod.get(pod_id)
                if latest is None or ts >= latest.get("ts", ""):
                    latest_by_pod[pod_id] = {
                        "ts": ts,
                        "nav": float(repaired.get("nav") or 0.0),
                        "quality": quality,
                    }

        return {
            "total_rows": len(raw_rows),
            "repaired_rows": repaired_count,
            "quality_counts": dict(quality_counts),
            "first_ts": first_ts,
            "last_ts": last_ts,
            "latest_by_pod": latest_by_pod,
        }

    def repair_collapsed_snapshots(self) -> int:
        """Rewrite existing collapsed placeholder rows to the previous valid NAV.

        Returns the number of rows updated.
        """
        cursor = self._conn.execute(
            """
            SELECT id, pod_id, ts, nav, cash, invested, realized
            FROM nav_snapshots
            ORDER BY ts ASC, id ASC
            """
        )
        raw_rows = [dict(row) for row in cursor.fetchall()]
        original_by_id = {row["id"]: row for row in raw_rows}
        seed_repaired = self._repair_leading_seed_placeholders(raw_rows)
        previous_by_pod: dict[str, dict] = {}
        updates: list[tuple[float, float, float, float, int]] = []
        for row in seed_repaired:
            original = original_by_id.get(row["id"], {})
            if any(
                float(row.get(key) or 0.0) != float(original.get(key) or 0.0)
                for key in ("nav", "cash", "invested", "realized")
            ):
                updates.append((
                    float(row["nav"]),
                    float(row["cash"]),
                    float(row["invested"]),
                    float(row["realized"]),
                    row["id"],
                ))
            pod_id = row.get("pod_id", "")
            previous = previous_by_pod.get(pod_id)
            if self._looks_like_collapsed_placeholder(row, previous):
                frozen = self._freeze_row_at_previous(row, previous)
                updates.append((
                    frozen["nav"],
                    frozen["cash"],
                    frozen["invested"],
                    frozen["realized"],
                    row["id"],
                ))
                previous_by_pod[pod_id] = frozen
            else:
                previous_by_pod[pod_id] = row

        if updates:
            self._conn.executemany(
                """
                UPDATE nav_snapshots
                SET nav = ?, cash = ?, invested = ?, realized = ?
                WHERE id = ?
                """,
                updates,
            )
            self._conn.commit()
        return len(updates)

    def close(self) -> None:
        """Close the SQLite connection.

        Must be called before process exit on Windows to release the
        file lock.
        """
        try:
            self._conn.close()
        except Exception:
            pass
