from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import duckdb


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


def parse_ts(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else [], default=str, sort_keys=True)


def json_loads(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def stable_hash(value: Any) -> str:
    if value is None:
        return ""
    payload = json_dumps(value) if not isinstance(value, str) else value
    return hashlib.sha256(payload.encode("utf-8", errors="ignore")).hexdigest()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def redact_summary(value: Any, max_chars: int = 1200) -> str:
    """Return a compact, low-risk summary string for traces/reports."""
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json_dumps(value)
        except Exception:
            text = str(value)
    text = " ".join(text.replace("\r", " ").replace("\n", " ").split())
    return text[:max_chars]


class _DuckStore:
    def __init__(self, db_path: str = ":memory:") -> None:
        self._db_path = db_path
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(db_path)

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass


class AgentRunStore(_DuckStore):
    """Durable, prompt-light ledger of meaningful agent/service runs."""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS agent_runs (
        run_id VARCHAR PRIMARY KEY,
        parent_run_id VARCHAR,
        agent_id VARCHAR,
        agent_type VARCHAR,
        pod_id VARCHAR,
        trigger VARCHAR,
        status VARCHAR,
        started_at VARCHAR,
        ended_at VARCHAR,
        duration_ms DOUBLE,
        model_provider VARCHAR,
        model_name VARCHAR,
        task VARCHAR,
        token_estimate INTEGER,
        cost_estimate DOUBLE,
        model_tier VARCHAR,
        model_selection_reason VARCHAR,
        budget_mode VARCHAR,
        fallback_path VARCHAR,
        input_hash VARCHAR,
        output_summary VARCHAR,
        error VARCHAR,
        artifact_refs VARCHAR
    )
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        super().__init__(db_path)
        self._conn.execute(self.SCHEMA)
        self._ensure_v3_columns()

    def _ensure_v3_columns(self) -> None:
        for column, dtype in (
            ("model_tier", "VARCHAR"),
            ("model_selection_reason", "VARCHAR"),
            ("budget_mode", "VARCHAR"),
            ("fallback_path", "VARCHAR"),
        ):
            try:
                self._conn.execute(f"ALTER TABLE agent_runs ADD COLUMN {column} {dtype}")
            except Exception:
                pass

    def start_run(
        self,
        *,
        agent_id: str,
        agent_type: str,
        pod_id: str | None = None,
        trigger: str = "",
        task: str = "",
        parent_run_id: str | None = None,
        model_provider: str = "",
        model_name: str = "",
        token_estimate: int | None = None,
        cost_estimate: float | None = None,
        model_tier: str = "",
        model_selection_reason: str = "",
        budget_mode: str = "",
        fallback_path: str = "",
        input_payload: Any = None,
        artifact_refs: list[str] | None = None,
    ) -> str:
        run_id = new_id("run")
        self._conn.execute(
            """
            INSERT INTO agent_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                run_id,
                parent_run_id or "",
                agent_id,
                agent_type,
                pod_id or "",
                trigger,
                "running",
                iso_now(),
                "",
                None,
                model_provider,
                model_name,
                task,
                token_estimate,
                cost_estimate,
                model_tier,
                model_selection_reason,
                budget_mode,
                fallback_path,
                stable_hash(input_payload),
                "",
                "",
                json_dumps(artifact_refs or []),
            ],
        )
        return run_id

    def complete_run(
        self,
        run_id: str,
        *,
        status: str = "success",
        output_summary: Any = "",
        artifact_refs: list[str] | None = None,
        model_provider: str | None = None,
        model_name: str | None = None,
        token_estimate: int | None = None,
        cost_estimate: float | None = None,
        model_tier: str | None = None,
        model_selection_reason: str | None = None,
        budget_mode: str | None = None,
        fallback_path: str | None = None,
    ) -> None:
        row = self.get_run(run_id)
        started = parse_ts(row.get("started_at")) if row else None
        ended = utc_now()
        duration_ms = ((ended - started).total_seconds() * 1000.0) if started else None
        existing_refs = json_loads(row.get("artifact_refs") if row else None, [])
        refs = artifact_refs if artifact_refs is not None else existing_refs
        self._conn.execute(
            """
            UPDATE agent_runs
            SET status=?, ended_at=?, duration_ms=?, output_summary=?, error='',
                artifact_refs=?, model_provider=COALESCE(?, model_provider),
                model_name=COALESCE(?, model_name), token_estimate=COALESCE(?, token_estimate),
                cost_estimate=COALESCE(?, cost_estimate), model_tier=COALESCE(?, model_tier),
                model_selection_reason=COALESCE(?, model_selection_reason),
                budget_mode=COALESCE(?, budget_mode), fallback_path=COALESCE(?, fallback_path)
            WHERE run_id=?
            """,
            [
                status,
                ended.isoformat(),
                duration_ms,
                redact_summary(output_summary),
                json_dumps(refs or []),
                model_provider,
                model_name,
                token_estimate,
                cost_estimate,
                model_tier,
                model_selection_reason,
                budget_mode,
                fallback_path,
                run_id,
            ],
        )

    def fail_run(self, run_id: str, error: Any, *, status: str = "failed", output_summary: Any = "") -> None:
        row = self.get_run(run_id)
        started = parse_ts(row.get("started_at")) if row else None
        ended = utc_now()
        duration_ms = ((ended - started).total_seconds() * 1000.0) if started else None
        self._conn.execute(
            """
            UPDATE agent_runs
            SET status=?, ended_at=?, duration_ms=?, output_summary=?, error=?
            WHERE run_id=?
            """,
            [status, ended.isoformat(), duration_ms, redact_summary(output_summary), redact_summary(error, 1000), run_id],
        )

    def get_run(self, run_id: str) -> dict:
        rows = self._conn.execute("SELECT * FROM agent_runs WHERE run_id=?", [run_id]).fetchall()
        cols = [d[0] for d in self._conn.description] if self._conn.description else []
        return self._decode(dict(zip(cols, rows[0]))) if rows else {}

    def list_runs(
        self,
        *,
        limit: int = 100,
        pod_id: str | None = None,
        status: str | None = None,
        agent_type: str | None = None,
        task: str | None = None,
    ) -> list[dict]:
        clauses: list[str] = []
        params: list[Any] = []
        if pod_id:
            clauses.append("pod_id=?")
            params.append(pod_id)
        if status:
            clauses.append("LOWER(status)=LOWER(?)")
            params.append(status)
        if agent_type:
            clauses.append("agent_type=?")
            params.append(agent_type)
        if task:
            clauses.append("task=?")
            params.append(task)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        limit = max(1, min(int(limit or 100), 1000))
        rows = self._conn.execute(
            f"SELECT * FROM agent_runs {where} ORDER BY started_at DESC LIMIT ?",
            params + [limit],
        ).fetchall()
        cols = [d[0] for d in self._conn.description] if self._conn.description else []
        return [self._decode(dict(zip(cols, row))) for row in rows]

    def summary(self, limit: int = 500) -> dict:
        rows = self.list_runs(limit=limit)
        failed = [r for r in rows if str(r.get("status", "")).lower() in {"failed", "error"}]
        slow = sorted(
            [r for r in rows if r.get("duration_ms") is not None],
            key=lambda x: float(x.get("duration_ms") or 0.0),
            reverse=True,
        )[:10]
        by_agent: dict[str, int] = {}
        by_model: dict[str, int] = {}
        for row in rows:
            by_agent[row.get("agent_type") or "unknown"] = by_agent.get(row.get("agent_type") or "unknown", 0) + 1
            model_key = "/".join(x for x in [row.get("model_provider"), row.get("model_name")] if x)
            if model_key:
                by_model[model_key] = by_model.get(model_key, 0) + 1
        return {
            "generated_at": iso_now(),
            "count": len(rows),
            "failed_count": len(failed),
            "running_count": sum(1 for r in rows if r.get("status") == "running"),
            "recent": rows[:50],
            "failed": failed[:25],
            "slow": slow,
            "by_agent_type": by_agent,
            "by_model": by_model,
        }

    @staticmethod
    def _decode(row: dict) -> dict:
        row["artifact_refs"] = json_loads(row.get("artifact_refs"), [])
        return row


class ArtifactRegistry(_DuckStore):
    """Named artefact freshness/status registry for dependency checks."""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS artifacts (
        artifact_id VARCHAR PRIMARY KEY,
        kind VARCHAR,
        owner VARCHAR,
        status VARCHAR,
        freshness_seconds DOUBLE,
        created_at VARCHAR,
        expires_at VARCHAR,
        source_run_id VARCHAR,
        payload_ref VARCHAR,
        updated_at VARCHAR
    )
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        super().__init__(db_path)
        self._conn.execute(self.SCHEMA)

    def record(
        self,
        *,
        kind: str,
        owner: str = "system",
        status: str = "fresh",
        freshness_seconds: float | None = None,
        expires_at: datetime | str | None = None,
        source_run_id: str = "",
        payload_ref: str = "",
        artifact_id: str | None = None,
        created_at: datetime | str | None = None,
    ) -> str:
        now = iso_now()
        created = created_at.isoformat() if isinstance(created_at, datetime) else (created_at or now)
        if isinstance(expires_at, datetime):
            expires = expires_at.isoformat()
        elif expires_at:
            expires = str(expires_at)
        elif freshness_seconds:
            expires = (utc_now() + timedelta(seconds=float(freshness_seconds))).isoformat()
        else:
            expires = ""
        artifact_id = artifact_id or f"{owner}:{kind}"
        self._conn.execute(
            """
            INSERT OR REPLACE INTO artifacts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                artifact_id,
                kind,
                owner,
                status,
                freshness_seconds,
                created,
                expires,
                source_run_id,
                payload_ref,
                now,
            ],
        )
        return artifact_id

    def list_artifacts(self, *, owner: str | None = None, kind: str | None = None, limit: int = 500) -> list[dict]:
        clauses: list[str] = []
        params: list[Any] = []
        if owner:
            clauses.append("owner=?")
            params.append(owner)
        if kind:
            clauses.append("kind=?")
            params.append(kind)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        limit = max(1, min(int(limit or 500), 1000))
        rows = self._conn.execute(
            f"SELECT * FROM artifacts {where} ORDER BY updated_at DESC LIMIT ?",
            params + [limit],
        ).fetchall()
        cols = [d[0] for d in self._conn.description] if self._conn.description else []
        return [self._with_freshness(dict(zip(cols, row))) for row in rows]

    def latest(self, kind: str, owner: str | None = None) -> dict:
        rows = self.list_artifacts(owner=owner, kind=kind, limit=1)
        return rows[0] if rows else {}

    def check_dependency(
        self,
        kind: str,
        *,
        owner: str | None = None,
        hard: bool = False,
        max_age_seconds: float | None = None,
    ) -> dict:
        artifact = self.latest(kind, owner)
        if not artifact:
            return {
                "kind": kind,
                "owner": owner or "",
                "status": "missing",
                "ok": False,
                "hard": hard,
                "action": "block" if hard else "degrade",
                "reason": f"Missing required artefact: {kind}",
            }
        stale = bool(artifact.get("is_expired"))
        if max_age_seconds is not None and artifact.get("age_seconds") is not None:
            stale = stale or float(artifact.get("age_seconds") or 0.0) > float(max_age_seconds)
        bad_status = str(artifact.get("status") or "").lower() in {"failed", "invalid", "stale", "missing"}
        ok = not stale and not bad_status
        return {
            **artifact,
            "ok": ok,
            "hard": hard,
            "action": "pass" if ok else ("block" if hard else "degrade"),
            "reason": "" if ok else f"{kind} is {artifact.get('status') or 'stale/missing'}",
        }

    def summary(self) -> dict:
        rows = self.list_artifacts(limit=1000)
        stale = [r for r in rows if r.get("is_expired") or str(r.get("status", "")).lower() in {"stale", "failed", "invalid"}]
        by_kind: dict[str, int] = {}
        by_status: dict[str, int] = {}
        for row in rows:
            by_kind[row.get("kind") or "unknown"] = by_kind.get(row.get("kind") or "unknown", 0) + 1
            by_status[row.get("status") or "unknown"] = by_status.get(row.get("status") or "unknown", 0) + 1
        return {
            "generated_at": iso_now(),
            "artifacts": rows,
            "count": len(rows),
            "stale_count": len(stale),
            "by_kind": by_kind,
            "by_status": by_status,
        }

    @staticmethod
    def _with_freshness(row: dict) -> dict:
        created = parse_ts(row.get("created_at"))
        expires = parse_ts(row.get("expires_at"))
        now = utc_now()
        row["age_seconds"] = round((now - created).total_seconds(), 1) if created else None
        row["is_expired"] = bool(expires and now > expires)
        return row


class ReportStore(_DuckStore):
    """Agent-readable structured report corpus, separate from raw logs."""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS report_corpus (
        report_id VARCHAR PRIMARY KEY,
        report_type VARCHAR,
        pod_id VARCHAR,
        symbol VARCHAR,
        related_run_ids VARCHAR,
        related_catalyst_ids VARCHAR,
        title VARCHAR,
        summary VARCHAR,
        body_markdown VARCHAR,
        created_at VARCHAR,
        tags VARCHAR,
        quality_flags VARCHAR
    )
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        super().__init__(db_path)
        self._conn.execute(self.SCHEMA)

    def add_report(
        self,
        *,
        report_type: str,
        title: str,
        summary: str,
        body_markdown: str = "",
        pod_id: str = "",
        symbol: str = "",
        related_run_ids: list[str] | None = None,
        related_catalyst_ids: list[str] | None = None,
        tags: list[str] | None = None,
        quality_flags: list[str] | None = None,
        report_id: str | None = None,
        created_at: str | None = None,
    ) -> str:
        report_id = report_id or new_id("report")
        self._conn.execute(
            """
            INSERT OR REPLACE INTO report_corpus VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                report_id,
                report_type,
                pod_id,
                symbol.upper() if symbol else "",
                json_dumps(related_run_ids or []),
                json_dumps(related_catalyst_ids or []),
                redact_summary(title, 300),
                redact_summary(summary, 1000),
                body_markdown or summary or "",
                created_at or iso_now(),
                json_dumps(tags or []),
                json_dumps(quality_flags or []),
            ],
        )
        return report_id

    def list_reports(
        self,
        *,
        limit: int = 100,
        pod_id: str | None = None,
        symbol: str | None = None,
        report_type: str | None = None,
        catalyst_id: str | None = None,
        factor: str | None = None,
        since: str | None = None,
        until: str | None = None,
    ) -> list[dict]:
        limit = max(1, min(int(limit or 100), 1000))
        clauses: list[str] = []
        params: list[Any] = []
        if pod_id:
            clauses.append("pod_id=?")
            params.append(pod_id)
        if symbol:
            clauses.append("symbol=?")
            params.append(symbol.upper())
        if report_type:
            clauses.append("report_type=?")
            params.append(report_type)
        if since:
            clauses.append("created_at>=?")
            params.append(since)
        if until:
            clauses.append("created_at<=?")
            params.append(until)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._conn.execute(
            f"SELECT * FROM report_corpus {where} ORDER BY created_at DESC LIMIT ?",
            params + [limit * 5 if (catalyst_id or factor) else limit],
        ).fetchall()
        cols = [d[0] for d in self._conn.description] if self._conn.description else []
        decoded = [self._decode(dict(zip(cols, row))) for row in rows]
        if catalyst_id:
            decoded = [r for r in decoded if catalyst_id in (r.get("related_catalyst_ids") or [])]
        if factor:
            needle = factor.lower()
            decoded = [
                r for r in decoded
                if needle in " ".join(
                    [
                        " ".join(str(t) for t in (r.get("tags") or [])),
                        r.get("title") or "",
                        r.get("summary") or "",
                        r.get("body_markdown") or "",
                    ]
                ).lower()
            ]
        return decoded[:limit]

    def decision_trace(
        self,
        *,
        limit: int = 100,
        pod_id: str | None = None,
        symbol: str | None = None,
        catalyst_id: str | None = None,
    ) -> dict:
        reports = self.list_reports(
            limit=limit,
            pod_id=pod_id,
            symbol=symbol,
            catalyst_id=catalyst_id,
        )
        ordered_types = [
            "foresight_catalyst",
            "pm_decision",
            "specialist_brief",
            "committee_review",
            "thesis_review",
            "position_review",
            "loss_review",
            "hindsight_review",
        ]
        stages = []
        for report_type in ordered_types:
            rows = [r for r in reports if r.get("report_type") == report_type]
            if rows:
                stages.append({"stage": report_type, "reports": rows[:10], "count": len(rows)})
        return {
            "generated_at": iso_now(),
            "filters": {"pod_id": pod_id or "", "symbol": symbol or "", "catalyst_id": catalyst_id or ""},
            "stages": stages,
            "reports": reports,
            "count": len(reports),
        }

    def summary(self) -> dict:
        rows = self.list_reports(limit=1000)
        by_type: dict[str, int] = {}
        for row in rows:
            by_type[row.get("report_type") or "unknown"] = by_type.get(row.get("report_type") or "unknown", 0) + 1
        return {
            "generated_at": iso_now(),
            "reports": rows[:100],
            "count": len(rows),
            "by_type": by_type,
        }

    @staticmethod
    def _decode(row: dict) -> dict:
        row["related_run_ids"] = json_loads(row.get("related_run_ids"), [])
        row["related_catalyst_ids"] = json_loads(row.get("related_catalyst_ids"), [])
        row["tags"] = json_loads(row.get("tags"), [])
        row["quality_flags"] = json_loads(row.get("quality_flags"), [])
        return row


@dataclass
class BudgetPolicy:
    max_specialist_requests_per_pm_cycle: int = 3
    max_ic_revision_rounds: int = 1
    max_llm_retries_per_task: int = 3
    daily_cost_warning_threshold: float = 100.0
    max_failed_model_calls_before_degraded: int = 5


class BudgetTracker(_DuckStore):
    SCHEMA = """
    CREATE TABLE IF NOT EXISTS budget_usage (
        usage_id VARCHAR PRIMARY KEY,
        ts VARCHAR,
        pod_id VARCHAR,
        agent_type VARCHAR,
        task VARCHAR,
        provider VARCHAR,
        model VARCHAR,
        status VARCHAR,
        token_estimate INTEGER,
        cost_estimate DOUBLE,
        error VARCHAR,
        run_id VARCHAR
    )
    """

    def __init__(self, db_path: str = ":memory:", policy: BudgetPolicy | None = None) -> None:
        super().__init__(db_path)
        self._conn.execute(self.SCHEMA)
        self.policy = policy or BudgetPolicy()

    def record_usage(
        self,
        *,
        pod_id: str = "",
        agent_type: str = "",
        task: str = "",
        provider: str = "",
        model: str = "",
        status: str = "",
        token_estimate: int | None = None,
        cost_estimate: float | None = None,
        error: str = "",
        run_id: str = "",
        ts: str | None = None,
        usage_id: str | None = None,
    ) -> str:
        ts = ts or iso_now()
        usage_id = usage_id or "usage_" + stable_hash([ts, pod_id, agent_type, task, provider, model, status])[:18]
        self._conn.execute(
            """
            INSERT OR REPLACE INTO budget_usage VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                usage_id,
                ts,
                pod_id,
                agent_type,
                task,
                provider,
                model,
                status,
                token_estimate,
                cost_estimate,
                redact_summary(error, 500),
                run_id,
            ],
        )
        return usage_id

    def ingest_llm_health(self, health: dict) -> None:
        for row in health.get("recent", []) or []:
            ts = str(row.get("ts") or iso_now())
            usage_id = "llm_" + stable_hash([
                ts,
                row.get("provider"),
                row.get("model"),
                row.get("task"),
                row.get("status"),
                row.get("fallback_attempt"),
            ])[:24]
            self.record_usage(
                task=str(row.get("task") or ""),
                provider=str(row.get("provider") or ""),
                model=str(row.get("model") or ""),
                status=str(row.get("status") or ""),
                token_estimate=row.get("total_tokens") or row.get("token_estimate"),
                cost_estimate=row.get("cost_estimate"),
                error=str(row.get("error") or ""),
                ts=ts,
                usage_id=usage_id,
            )

    def list_usage(self, *, limit: int = 500) -> list[dict]:
        limit = max(1, min(int(limit or 500), 2000))
        rows = self._conn.execute(
            "SELECT * FROM budget_usage ORDER BY ts DESC LIMIT ?",
            [limit],
        ).fetchall()
        cols = [d[0] for d in self._conn.description] if self._conn.description else []
        return [dict(zip(cols, row)) for row in rows]

    def summary(self, *, limit: int = 1000) -> dict:
        rows = self.list_usage(limit=limit)
        today = utc_now().date()
        today_rows = []
        for row in rows:
            parsed = parse_ts(row.get("ts"))
            if parsed and parsed.date() == today:
                today_rows.append(row)
        failed = [r for r in today_rows if str(r.get("status", "")).lower() not in {"success", "ok", ""}]
        fallback_rows = [r for r in today_rows if str(r.get("provider") or "").lower() not in {"openai", ""}]
        cost = sum(float(r.get("cost_estimate") or 0.0) for r in today_rows)
        tokens = sum(int(r.get("token_estimate") or 0) for r in today_rows)
        by_task: dict[str, dict] = {}
        by_model: dict[str, dict] = {}
        for row in today_rows:
            self._bump(by_task, row.get("task") or "unknown", row)
            model_key = "/".join(x for x in [row.get("provider"), row.get("model")] if x) or "unknown"
            self._bump(by_model, model_key, row)
        degraded = len(failed) >= self.policy.max_failed_model_calls_before_degraded
        return {
            "generated_at": iso_now(),
            "policy": self.policy.__dict__,
            "today": {
                "calls": len(today_rows),
                "failures": len(failed),
                "fallback_calls": len(fallback_rows),
                "fallback_rate": round(len(fallback_rows) / len(today_rows), 4) if today_rows else 0.0,
                "token_estimate": tokens,
                "cost_estimate": round(cost, 6),
                "warning": cost >= self.policy.daily_cost_warning_threshold,
                "degraded": degraded,
                "degraded_reason": (
                    f"{len(failed)} failed model/tool calls today"
                    if degraded else ""
                ),
            },
            "by_task": sorted(by_task.values(), key=lambda x: x["calls"], reverse=True),
            "by_model": sorted(by_model.values(), key=lambda x: x["calls"], reverse=True),
            "recent": rows[:100],
        }

    @staticmethod
    def _bump(bucket: dict[str, dict], key: str, row: dict) -> None:
        stat = bucket.setdefault(key, {"key": key, "calls": 0, "successes": 0, "failures": 0, "cost_estimate": 0.0})
        stat["calls"] += 1
        if str(row.get("status", "")).lower() in {"success", "ok"}:
            stat["successes"] += 1
        elif row.get("status"):
            stat["failures"] += 1
        stat["cost_estimate"] = round(float(stat["cost_estimate"]) + float(row.get("cost_estimate") or 0.0), 6)


class SchedulerJobRegistry(_DuckStore):
    SCHEMA = """
    CREATE TABLE IF NOT EXISTS scheduler_jobs (
        job_name VARCHAR PRIMARY KEY,
        status VARCHAR,
        trigger VARCHAR,
        started_at VARCHAR,
        ended_at VARCHAR,
        duration_ms DOUBLE,
        run_id VARCHAR,
        last_error VARCHAR,
        skipped_count INTEGER,
        run_count INTEGER,
        updated_at VARCHAR
    )
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        super().__init__(db_path)
        self._conn.execute(self.SCHEMA)

    def start_job(self, job_name: str, *, trigger: str = "", run_id: str = "", stale_after_seconds: float = 3600.0) -> tuple[bool, dict]:
        current = self.get_job(job_name)
        now = utc_now()
        if current.get("status") == "running":
            started = parse_ts(current.get("started_at"))
            if started and (now - started).total_seconds() < stale_after_seconds:
                skipped = int(current.get("skipped_count") or 0) + 1
                self._conn.execute(
                    "UPDATE scheduler_jobs SET skipped_count=?, updated_at=? WHERE job_name=?",
                    [skipped, now.isoformat(), job_name],
                )
                current["skipped_count"] = skipped
                return False, current
        self._conn.execute(
            """
            INSERT OR REPLACE INTO scheduler_jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                job_name,
                "running",
                trigger,
                now.isoformat(),
                "",
                None,
                run_id,
                "",
                int(current.get("skipped_count") or 0),
                int(current.get("run_count") or 0),
                now.isoformat(),
            ],
        )
        return True, self.get_job(job_name)

    def complete_job(self, job_name: str, *, status: str = "success", error: str = "") -> None:
        current = self.get_job(job_name)
        now = utc_now()
        started = parse_ts(current.get("started_at"))
        duration_ms = ((now - started).total_seconds() * 1000.0) if started else None
        run_count = int(current.get("run_count") or 0) + (1 if status == "success" else 0)
        self._conn.execute(
            """
            UPDATE scheduler_jobs
            SET status=?, ended_at=?, duration_ms=?, last_error=?, run_count=?, updated_at=?
            WHERE job_name=?
            """,
            [status, now.isoformat(), duration_ms, redact_summary(error, 1000), run_count, now.isoformat(), job_name],
        )

    def fail_job(self, job_name: str, error: Any) -> None:
        self.complete_job(job_name, status="failed", error=redact_summary(error, 1000))

    def get_job(self, job_name: str) -> dict:
        rows = self._conn.execute("SELECT * FROM scheduler_jobs WHERE job_name=?", [job_name]).fetchall()
        cols = [d[0] for d in self._conn.description] if self._conn.description else []
        return dict(zip(cols, rows[0])) if rows else {}

    def list_jobs(self) -> list[dict]:
        rows = self._conn.execute("SELECT * FROM scheduler_jobs ORDER BY updated_at DESC").fetchall()
        cols = [d[0] for d in self._conn.description] if self._conn.description else []
        return [dict(zip(cols, row)) for row in rows]

    def summary(self) -> dict:
        jobs = self.list_jobs()
        return {
            "generated_at": iso_now(),
            "jobs": jobs,
            "count": len(jobs),
            "running_count": sum(1 for j in jobs if j.get("status") == "running"),
            "failed_count": sum(1 for j in jobs if j.get("status") == "failed"),
        }


class HindsightService:
    """Advisory reviewer for expired catalysts/theses/briefs/IC records."""

    SOURCE_TYPES = {"foresight_catalyst", "pm_decision", "specialist_brief", "committee_review", "thesis_review"}

    def __init__(self, report_store: ReportStore) -> None:
        self._reports = report_store

    def run_once(self, *, max_items: int = 25, min_age_hours: float = 24.0, outcome_context: dict | None = None) -> dict:
        now = utc_now()
        outcome_context = outcome_context or {}
        sources = self._reports.list_reports(limit=500)
        existing = self._reports.list_reports(limit=1000, report_type="hindsight_review")
        reviewed_ids = set()
        for report in existing:
            for tag in report.get("tags") or []:
                if str(tag).startswith("source_report:"):
                    reviewed_ids.add(str(tag).split(":", 1)[1])

        created: list[str] = []
        review_rows: list[dict] = []
        skipped = 0
        for report in sources:
            if len(created) >= max_items:
                break
            report_id = str(report.get("report_id") or "")
            if not report_id or report_id in reviewed_ids or report.get("report_type") not in self.SOURCE_TYPES:
                continue
            created_at = parse_ts(report.get("created_at"))
            if created_at and (now - created_at).total_seconds() < min_age_hours * 3600:
                skipped += 1
                continue
            summary = self._grade_report(report, outcome_context=outcome_context)
            hid = self._reports.add_report(
                report_id=f"hindsight_{report_id}",
                report_type="hindsight_review",
                pod_id=report.get("pod_id") or "",
                symbol=report.get("symbol") or "",
                related_run_ids=report.get("related_run_ids") or [],
                related_catalyst_ids=report.get("related_catalyst_ids") or [],
                title=f"Hindsight: {report.get('title') or report_id}",
                summary=summary["summary"],
                body_markdown=summary["body_markdown"],
                tags=["hindsight", f"source_report:{report_id}", f"source_type:{report.get('report_type')}"],
                quality_flags=summary["quality_flags"],
            )
            created.append(hid)
            review_rows.append({
                "report_id": hid,
                "source_report_id": report_id,
                "related_catalyst_ids": report.get("related_catalyst_ids") or [],
                "hindsight_score": summary.get("hindsight_score"),
            })
        return {
            "generated_at": iso_now(),
            "created_count": len(created),
            "created_report_ids": created,
            "reviews": review_rows,
            "skipped_not_expired": skipped,
        }

    @staticmethod
    def _grade_report(report: dict, outcome_context: dict | None = None) -> dict:
        outcome_context = outcome_context or {}
        report_type = report.get("report_type") or "report"
        flags: list[str] = []
        text = f"{report.get('summary', '')} {report.get('body_markdown', '')}".lower()
        if any(term in text for term in ["uncertain", "mixed", "if ", "unless", "risk"]):
            flags.append("conditional_reasoning_present")
        else:
            flags.append("limited_uncertainty_language")
        if any(term in text for term in ["invalidation", "stop", "exit", "prove wrong"]):
            flags.append("invalidation_present")
        else:
            flags.append("missing_invalidation")
        symbol = str(report.get("symbol") or "").upper()
        pod_id = str(report.get("pod_id") or "")
        symbol_outcome = (outcome_context.get("symbols") or {}).get(symbol, {}) if symbol else {}
        pod_outcome = (outcome_context.get("pods") or {}).get(pod_id, {}) if pod_id else {}
        pnl = symbol_outcome.get("pnl")
        pnl_pct = symbol_outcome.get("pnl_pct")
        direction_score = HindsightService._direction_score(text, pnl, pnl_pct)
        timing_score = 0.5
        if "immediate" in text or "24h" in text:
            timing_score = 0.6 if symbol_outcome.get("updated_recently") else 0.4
        evidence_score = 0.35
        evidence_score += 0.20 if "conditional_reasoning_present" in flags else 0.0
        evidence_score += 0.20 if "invalidation_present" in flags else 0.0
        evidence_score += 0.15 if symbol_outcome or pod_outcome else 0.0
        evidence_score = max(0.0, min(1.0, evidence_score))
        hindsight_score = round((direction_score * 0.45) + (timing_score * 0.20) + (evidence_score * 0.35), 4)
        if direction_score >= 0.65:
            flags.append("direction_supported")
        elif direction_score <= 0.35:
            flags.append("direction_challenged")
        summary = (
            f"Hindsight score {hindsight_score:.2f} for {report_type}: "
            f"direction={direction_score:.2f}, timing={timing_score:.2f}, evidence={evidence_score:.2f}."
        )
        body = (
            "## Hindsight Review\n\n"
            f"- Source report: `{report.get('report_id')}`\n"
            f"- Source type: `{report_type}`\n"
            f"- Pod: `{report.get('pod_id') or 'n/a'}`\n"
            f"- Symbol: `{report.get('symbol') or 'n/a'}`\n\n"
            "### Questions\n"
            f"- Hindsight score: `{hindsight_score:.2f}`\n"
            f"- Direction score: `{direction_score:.2f}`\n"
            f"- Timing score: `{timing_score:.2f}`\n"
            f"- Evidence score: `{evidence_score:.2f}`\n"
            f"- Symbol outcome: `{json_dumps(symbol_outcome) if symbol_outcome else 'n/a'}`\n"
            f"- Pod outcome: `{json_dumps(pod_outcome) if pod_outcome else 'n/a'}`\n\n"
            "### Quality Flags\n"
            + "\n".join(f"- `{flag}`" for flag in flags)
        )
        return {"summary": summary, "body_markdown": body, "quality_flags": flags, "hindsight_score": hindsight_score}

    @staticmethod
    def _direction_score(text: str, pnl: Any, pnl_pct: Any) -> float:
        try:
            outcome = float(pnl_pct if pnl_pct is not None else pnl)
        except (TypeError, ValueError):
            return 0.5
        bullish = any(word in text for word in ("buy", "long", "bullish", "upside", "benefit", "positive"))
        bearish = any(word in text for word in ("sell", "short", "bearish", "downside", "negative", "reduce"))
        if bullish and not bearish:
            return 0.75 if outcome > 0 else 0.25 if outcome < 0 else 0.5
        if bearish and not bullish:
            return 0.75 if outcome < 0 else 0.25 if outcome > 0 else 0.5
        return 0.5 if abs(outcome) < 0.001 else 0.55


class DecisionReplayStore(_DuckStore):
    """Durable decision snapshots, lightweight evaluations, and dry-run replay reports."""

    SNAPSHOT_SCHEMA = """
    CREATE TABLE IF NOT EXISTS decision_snapshots (
        snapshot_id VARCHAR PRIMARY KEY,
        decision_id VARCHAR,
        pod_id VARCHAR,
        symbol VARCHAR,
        side VARCHAR,
        status VARCHAR,
        created_at VARCHAR,
        decision_horizon VARCHAR,
        horizon_end VARCHAR,
        price_at_decision DOUBLE,
        position_state VARCHAR,
        catalyst_ids VARCHAR,
        catalyst_state VARCHAR,
        signal_features VARCHAR,
        specialist_briefs VARCHAR,
        committee_review VARCHAR,
        thesis_fields VARCHAR,
        risk_state VARCHAR,
        artifact_status VARCHAR,
        model_trace_refs VARCHAR,
        report_refs VARCHAR
    )
    """
    EVALUATION_SCHEMA = """
    CREATE TABLE IF NOT EXISTS decision_evaluations (
        evaluation_id VARCHAR PRIMARY KEY,
        snapshot_id VARCHAR,
        pod_id VARCHAR,
        symbol VARCHAR,
        side VARCHAR,
        evaluated_at VARCHAR,
        horizon_met BOOLEAN,
        price_at_decision DOUBLE,
        price_at_evaluation DOUBLE,
        return_pct DOUBLE,
        pnl DOUBLE,
        pnl_pct DOUBLE,
        outcome VARCHAR,
        score DOUBLE,
        notes VARCHAR,
        missing_data VARCHAR,
        report_id VARCHAR
    )
    """
    REPLAY_SCHEMA = """
    CREATE TABLE IF NOT EXISTS shadow_replays (
        replay_id VARCHAR PRIMARY KEY,
        snapshot_id VARCHAR,
        pod_id VARCHAR,
        symbol VARCHAR,
        created_at VARCHAR,
        original_decision VARCHAR,
        replay_decision VARCHAR,
        changed BOOLEAN,
        comparison VARCHAR,
        dry_run BOOLEAN,
        state_mutation_detected BOOLEAN,
        execution_attempted BOOLEAN,
        report_id VARCHAR
    )
    """

    def __init__(self, db_path: str = ":memory:", reports: ReportStore | None = None) -> None:
        super().__init__(db_path)
        self._conn.execute(self.SNAPSHOT_SCHEMA)
        self._conn.execute(self.EVALUATION_SCHEMA)
        self._conn.execute(self.REPLAY_SCHEMA)
        self._reports = reports

    def add_snapshot(self, snapshot: dict) -> str:
        snapshot_id = snapshot.get("snapshot_id") or new_id("snap")
        created_at = snapshot.get("created_at") or iso_now()
        horizon_end = snapshot.get("horizon_end") or ""
        self._conn.execute(
            """
            INSERT OR REPLACE INTO decision_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                snapshot_id,
                snapshot.get("decision_id") or "",
                snapshot.get("pod_id") or "",
                str(snapshot.get("symbol") or "").upper(),
                str(snapshot.get("side") or "HOLD").upper(),
                snapshot.get("status") or "active",
                created_at,
                snapshot.get("decision_horizon") or "days",
                horizon_end,
                snapshot.get("price_at_decision"),
                json_dumps(snapshot.get("position_state") or {}),
                json_dumps(snapshot.get("catalyst_ids") or []),
                json_dumps(snapshot.get("catalyst_state") or []),
                json_dumps(snapshot.get("signal_features") or {}),
                json_dumps(snapshot.get("specialist_briefs") or []),
                json_dumps(snapshot.get("committee_review") or {}),
                json_dumps(snapshot.get("thesis_fields") or {}),
                json_dumps(snapshot.get("risk_state") or {}),
                json_dumps(snapshot.get("artifact_status") or {}),
                json_dumps(snapshot.get("model_trace_refs") or []),
                json_dumps(snapshot.get("report_refs") or []),
            ],
        )
        return snapshot_id

    def get_snapshot(self, snapshot_id: str) -> dict:
        rows = self._conn.execute("SELECT * FROM decision_snapshots WHERE snapshot_id=?", [snapshot_id]).fetchall()
        cols = [d[0] for d in self._conn.description] if self._conn.description else []
        return self._decode_snapshot(dict(zip(cols, rows[0]))) if rows else {}

    def update_snapshot_status(self, snapshot_id: str, status: str, details: dict | None = None) -> None:
        self._conn.execute("UPDATE decision_snapshots SET status=? WHERE snapshot_id=?", [status, snapshot_id])

    def list_snapshots(
        self,
        *,
        limit: int = 100,
        pod_id: str | None = None,
        symbol: str | None = None,
        status: str | None = None,
    ) -> list[dict]:
        clauses: list[str] = []
        params: list[Any] = []
        if pod_id:
            clauses.append("pod_id=?")
            params.append(pod_id)
        if symbol:
            clauses.append("symbol=?")
            params.append(symbol.upper())
        if status:
            clauses.append("status=?")
            params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        limit = max(1, min(int(limit or 100), 1000))
        rows = self._conn.execute(
            f"SELECT * FROM decision_snapshots {where} ORDER BY created_at DESC LIMIT ?",
            params + [limit],
        ).fetchall()
        cols = [d[0] for d in self._conn.description] if self._conn.description else []
        return [self._decode_snapshot(dict(zip(cols, row))) for row in rows]

    def evaluate_due(
        self,
        *,
        outcome_context: dict | None = None,
        max_items: int = 50,
        min_age_hours: float = 0.0,
    ) -> dict:
        outcome_context = outcome_context or {}
        existing = {row.get("snapshot_id") for row in self.list_evaluations(limit=2000)}
        now = utc_now()
        created: list[dict] = []
        for snapshot in self.list_snapshots(limit=1000):
            if len(created) >= max_items:
                break
            if snapshot.get("snapshot_id") in existing:
                continue
            created_at = parse_ts(snapshot.get("created_at"))
            horizon_end = parse_ts(snapshot.get("horizon_end"))
            if created_at and (now - created_at).total_seconds() < min_age_hours * 3600:
                continue
            if horizon_end and now < horizon_end:
                continue
            evaluation = self._evaluate_snapshot(snapshot, outcome_context)
            self.add_evaluation(evaluation)
            created.append(evaluation)
        return {"generated_at": iso_now(), "created_count": len(created), "evaluations": created}

    def add_evaluation(self, evaluation: dict) -> str:
        evaluation_id = evaluation.get("evaluation_id") or f"eval_{evaluation.get('snapshot_id') or new_id('snap')}"
        report_id = evaluation.get("report_id") or ""
        if self._reports and not report_id:
            report_id = self._reports.add_report(
                report_id=f"report_{evaluation_id}",
                report_type="decision_evaluation",
                pod_id=evaluation.get("pod_id") or "",
                symbol=evaluation.get("symbol") or "",
                title=f"Decision evaluation: {evaluation.get('side', 'HOLD')} {evaluation.get('symbol') or ''}".strip(),
                summary=evaluation.get("outcome") or "Decision evaluation",
                body_markdown=json.dumps(evaluation, default=str, indent=2),
                tags=["decision_evaluation", f"snapshot:{evaluation.get('snapshot_id') or ''}"],
                quality_flags=evaluation.get("notes") or [],
            )
            evaluation["report_id"] = report_id
        self._conn.execute(
            """
            INSERT OR REPLACE INTO decision_evaluations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                evaluation_id,
                evaluation.get("snapshot_id") or "",
                evaluation.get("pod_id") or "",
                str(evaluation.get("symbol") or "").upper(),
                str(evaluation.get("side") or "HOLD").upper(),
                evaluation.get("evaluated_at") or iso_now(),
                bool(evaluation.get("horizon_met")),
                evaluation.get("price_at_decision"),
                evaluation.get("price_at_evaluation"),
                evaluation.get("return_pct"),
                evaluation.get("pnl"),
                evaluation.get("pnl_pct"),
                evaluation.get("outcome") or "unknown",
                evaluation.get("score"),
                json_dumps(evaluation.get("notes") or []),
                json_dumps(evaluation.get("missing_data") or []),
                evaluation.get("report_id") or "",
            ],
        )
        return evaluation_id

    def list_evaluations(
        self,
        *,
        limit: int = 100,
        pod_id: str | None = None,
        symbol: str | None = None,
    ) -> list[dict]:
        clauses: list[str] = []
        params: list[Any] = []
        if pod_id:
            clauses.append("pod_id=?")
            params.append(pod_id)
        if symbol:
            clauses.append("symbol=?")
            params.append(symbol.upper())
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        limit = max(1, min(int(limit or 100), 1000))
        rows = self._conn.execute(
            f"SELECT * FROM decision_evaluations {where} ORDER BY evaluated_at DESC LIMIT ?",
            params + [limit],
        ).fetchall()
        cols = [d[0] for d in self._conn.description] if self._conn.description else []
        return [self._decode_evaluation(dict(zip(cols, row))) for row in rows]

    def record_shadow_replay(self, snapshot_id: str, replay_decision: dict | None = None) -> dict:
        snapshot = self.get_snapshot(snapshot_id)
        if not snapshot:
            return {"error": f"snapshot not found: {snapshot_id}", "dry_run": True}
        replay_decision = replay_decision or {
            "side": snapshot.get("side", "HOLD"),
            "symbol": snapshot.get("symbol", ""),
            "reason": "Dry-run replay used stored snapshot context; no live state mutation or execution was allowed.",
        }
        original = {
            "side": snapshot.get("side", "HOLD"),
            "symbol": snapshot.get("symbol", ""),
            "thesis_fields": snapshot.get("thesis_fields") or {},
        }
        changed = (str(original.get("side")) != str(replay_decision.get("side"))) or (
            str(original.get("symbol")) != str(replay_decision.get("symbol"))
        )
        result = {
            "replay_id": new_id("replay"),
            "snapshot_id": snapshot_id,
            "pod_id": snapshot.get("pod_id") or "",
            "symbol": snapshot.get("symbol") or "",
            "created_at": iso_now(),
            "original_decision": original,
            "replay_decision": replay_decision,
            "changed": changed,
            "comparison": "Replay decision changed." if changed else "Replay decision matched original side/symbol.",
            "dry_run": True,
            "state_mutation_detected": False,
            "execution_attempted": False,
            "report_id": "",
        }
        if self._reports:
            result["report_id"] = self._reports.add_report(
                report_id=f"report_{result['replay_id']}",
                report_type="shadow_replay",
                pod_id=result["pod_id"],
                symbol=result["symbol"],
                title=f"Shadow replay: {result['symbol'] or snapshot_id}",
                summary=result["comparison"],
                body_markdown=json.dumps(result, default=str, indent=2),
                tags=["shadow_replay", f"snapshot:{snapshot_id}", "dry_run"],
                quality_flags=[],
            )
        self._conn.execute(
            """
            INSERT OR REPLACE INTO shadow_replays VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                result["replay_id"],
                result["snapshot_id"],
                result["pod_id"],
                result["symbol"],
                result["created_at"],
                json_dumps(result["original_decision"]),
                json_dumps(result["replay_decision"]),
                bool(result["changed"]),
                result["comparison"],
                True,
                False,
                False,
                result.get("report_id") or "",
            ],
        )
        return result

    def list_shadow_replays(self, *, limit: int = 100, snapshot_id: str | None = None) -> list[dict]:
        clauses: list[str] = []
        params: list[Any] = []
        if snapshot_id:
            clauses.append("snapshot_id=?")
            params.append(snapshot_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        limit = max(1, min(int(limit or 100), 1000))
        rows = self._conn.execute(
            f"SELECT * FROM shadow_replays {where} ORDER BY created_at DESC LIMIT ?",
            params + [limit],
        ).fetchall()
        cols = [d[0] for d in self._conn.description] if self._conn.description else []
        return [self._decode_replay(dict(zip(cols, row))) for row in rows]

    @staticmethod
    def _evaluate_snapshot(snapshot: dict, outcome_context: dict) -> dict:
        symbol = str(snapshot.get("symbol") or "").upper()
        pod_id = str(snapshot.get("pod_id") or "")
        side = str(snapshot.get("side") or "HOLD").upper()
        outcome = (outcome_context.get("symbols") or {}).get(symbol, {}) if symbol else {}
        missing: list[str] = []
        notes: list[str] = []
        price0 = snapshot.get("price_at_decision")
        price1 = outcome.get("price") or outcome.get("current_price")
        try:
            p0 = float(price0) if price0 is not None else None
            p1 = float(price1) if price1 is not None else None
        except (TypeError, ValueError):
            p0, p1 = None, None
        ret = ((p1 - p0) / p0) if p0 and p1 is not None else outcome.get("return_pct")
        pnl = outcome.get("pnl")
        pnl_pct = outcome.get("pnl_pct", ret)
        if p0 is None:
            missing.append("price_at_decision")
        if p1 is None and ret is None and pnl_pct is None:
            missing.append("price_at_evaluation")
        score = 0.5
        label = "insufficient_data" if missing else "neutral"
        try:
            signal = float(pnl_pct if pnl_pct is not None else ret if ret is not None else 0.0)
            if side == "BUY":
                score = 0.75 if signal > 0 else 0.25 if signal < 0 else 0.5
                label = "supported" if signal > 0 else "challenged" if signal < 0 else "flat"
            elif side == "SELL":
                score = 0.75 if signal < 0 else 0.25 if signal > 0 else 0.5
                label = "supported" if signal < 0 else "challenged" if signal > 0 else "flat"
            elif side == "HOLD":
                score = 0.65 if abs(signal) < 0.01 else 0.45
                label = "quiet_hold" if abs(signal) < 0.01 else "missed_move"
        except Exception:
            pass
        if snapshot.get("catalyst_ids"):
            notes.append("catalyst_linked")
        else:
            notes.append("no_catalyst_link")
        return {
            "evaluation_id": f"eval_{snapshot.get('snapshot_id')}",
            "snapshot_id": snapshot.get("snapshot_id") or "",
            "pod_id": pod_id,
            "symbol": symbol,
            "side": side,
            "evaluated_at": iso_now(),
            "horizon_met": True,
            "price_at_decision": p0,
            "price_at_evaluation": p1,
            "return_pct": ret,
            "pnl": pnl,
            "pnl_pct": pnl_pct,
            "outcome": label,
            "score": score,
            "notes": notes,
            "missing_data": missing,
        }

    @staticmethod
    def _decode_snapshot(row: dict) -> dict:
        for key, default in (
            ("position_state", {}),
            ("catalyst_ids", []),
            ("catalyst_state", []),
            ("signal_features", {}),
            ("specialist_briefs", []),
            ("committee_review", {}),
            ("thesis_fields", {}),
            ("risk_state", {}),
            ("artifact_status", {}),
            ("model_trace_refs", []),
            ("report_refs", []),
        ):
            row[key] = json_loads(row.get(key), default)
        return row

    @staticmethod
    def _decode_evaluation(row: dict) -> dict:
        row["notes"] = json_loads(row.get("notes"), [])
        row["missing_data"] = json_loads(row.get("missing_data"), [])
        return row

    @staticmethod
    def _decode_replay(row: dict) -> dict:
        row["original_decision"] = json_loads(row.get("original_decision"), {})
        row["replay_decision"] = json_loads(row.get("replay_decision"), {})
        return row


class PortfolioConstructionStore(_DuckStore):
    SCHEMA = """
    CREATE TABLE IF NOT EXISTS portfolio_construction_reviews (
        review_id VARCHAR PRIMARY KEY,
        pod_id VARCHAR,
        symbol VARCHAR,
        side VARCHAR,
        requested_notional DOUBLE,
        recommended_notional DOUBLE,
        action VARCHAR,
        reason VARCHAR,
        duplicate_exposures VARCHAR,
        portfolio_impact VARCHAR,
        funding_suggestion VARCHAR,
        expected_factor_change VARCHAR,
        confidence DOUBLE,
        created_at VARCHAR,
        report_id VARCHAR
    )
    """

    def __init__(self, db_path: str = ":memory:", reports: ReportStore | None = None) -> None:
        super().__init__(db_path)
        self._conn.execute(self.SCHEMA)
        self._reports = reports

    def add_review(self, review: dict) -> str:
        review_id = review.get("review_id") or new_id("pc")
        report_id = review.get("report_id") or ""
        if self._reports and not report_id:
            report_id = self._reports.add_report(
                report_id=f"report_{review_id}",
                report_type="portfolio_construction",
                pod_id=review.get("pod_id") or "",
                symbol=review.get("symbol") or "",
                title=f"Portfolio construction: {review.get('side', '')} {review.get('symbol', '')}".strip(),
                summary=f"{review.get('action')}: {review.get('reason', '')}",
                body_markdown=json.dumps(review, default=str, indent=2),
                tags=["portfolio_construction", str(review.get("action") or "")],
                quality_flags=review.get("duplicate_exposures") or [],
            )
            review["report_id"] = report_id
        self._conn.execute(
            """
            INSERT OR REPLACE INTO portfolio_construction_reviews VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                review_id,
                review.get("pod_id") or "",
                str(review.get("symbol") or "").upper(),
                str(review.get("side") or "").upper(),
                float(review.get("requested_notional") or 0.0),
                float(review.get("recommended_notional") or 0.0),
                review.get("action") or "APPROVE_SIZE",
                redact_summary(review.get("reason") or "", 1000),
                json_dumps(review.get("duplicate_exposures") or []),
                json_dumps(review.get("portfolio_impact") or {}),
                redact_summary(review.get("funding_suggestion") or "", 500),
                json_dumps(review.get("expected_factor_change") or {}),
                float(review.get("confidence") or 0.5),
                review.get("created_at") or iso_now(),
                review.get("report_id") or "",
            ],
        )
        return review_id

    def list_reviews(self, *, limit: int = 100, pod_id: str | None = None, symbol: str | None = None) -> list[dict]:
        clauses: list[str] = []
        params: list[Any] = []
        if pod_id:
            clauses.append("pod_id=?")
            params.append(pod_id)
        if symbol:
            clauses.append("symbol=?")
            params.append(symbol.upper())
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        limit = max(1, min(int(limit or 100), 1000))
        rows = self._conn.execute(
            f"SELECT * FROM portfolio_construction_reviews {where} ORDER BY created_at DESC LIMIT ?",
            params + [limit],
        ).fetchall()
        cols = [d[0] for d in self._conn.description] if self._conn.description else []
        out = []
        for row in rows:
            item = dict(zip(cols, row))
            item["duplicate_exposures"] = json_loads(item.get("duplicate_exposures"), [])
            item["portfolio_impact"] = json_loads(item.get("portfolio_impact"), {})
            item["expected_factor_change"] = json_loads(item.get("expected_factor_change"), {})
            out.append(item)
        return out


class ThesisMonitorStore(_DuckStore):
    SCHEMA = """
    CREATE TABLE IF NOT EXISTS thesis_monitor_results (
        monitor_id VARCHAR PRIMARY KEY,
        pod_id VARCHAR,
        symbol VARCHAR,
        status VARCHAR,
        reason VARCHAR,
        triggers VARCHAR,
        catalyst_ids VARCHAR,
        thesis_age_days DOUBLE,
        max_hold_days INTEGER,
        created_at VARCHAR,
        report_id VARCHAR
    )
    """

    def __init__(self, db_path: str = ":memory:", reports: ReportStore | None = None) -> None:
        super().__init__(db_path)
        self._conn.execute(self.SCHEMA)
        self._reports = reports

    def add_result(self, result: dict) -> str:
        monitor_id = result.get("monitor_id") or new_id("thesis_monitor")
        report_id = result.get("report_id") or ""
        if self._reports and not report_id:
            report_id = self._reports.add_report(
                report_id=f"report_{monitor_id}",
                report_type="thesis_monitor",
                pod_id=result.get("pod_id") or "",
                symbol=result.get("symbol") or "",
                related_catalyst_ids=result.get("catalyst_ids") or [],
                title=f"Thesis monitor: {result.get('symbol') or ''}",
                summary=f"{result.get('status')}: {result.get('reason', '')}",
                body_markdown=json.dumps(result, default=str, indent=2),
                tags=["thesis_monitor", str(result.get("status") or "")],
                quality_flags=result.get("triggers") or [],
            )
            result["report_id"] = report_id
        self._conn.execute(
            """
            INSERT OR REPLACE INTO thesis_monitor_results VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                monitor_id,
                result.get("pod_id") or "",
                str(result.get("symbol") or "").upper(),
                result.get("status") or "THESIS_OK",
                redact_summary(result.get("reason") or "", 1000),
                json_dumps(result.get("triggers") or []),
                json_dumps(result.get("catalyst_ids") or []),
                result.get("thesis_age_days"),
                int(result.get("max_hold_days") or 0),
                result.get("created_at") or iso_now(),
                result.get("report_id") or "",
            ],
        )
        return monitor_id

    def list_results(self, *, limit: int = 100, pod_id: str | None = None, symbol: str | None = None) -> list[dict]:
        clauses: list[str] = []
        params: list[Any] = []
        if pod_id:
            clauses.append("pod_id=?")
            params.append(pod_id)
        if symbol:
            clauses.append("symbol=?")
            params.append(symbol.upper())
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        limit = max(1, min(int(limit or 100), 1000))
        rows = self._conn.execute(
            f"SELECT * FROM thesis_monitor_results {where} ORDER BY created_at DESC LIMIT ?",
            params + [limit],
        ).fetchall()
        cols = [d[0] for d in self._conn.description] if self._conn.description else []
        out = []
        for row in rows:
            item = dict(zip(cols, row))
            item["triggers"] = json_loads(item.get("triggers"), [])
            item["catalyst_ids"] = json_loads(item.get("catalyst_ids"), [])
            out.append(item)
        return out


class CalibrationStore(_DuckStore):
    SCHEMA = """
    CREATE TABLE IF NOT EXISTS calibration_scores (
        entity_type VARCHAR,
        entity_id VARCHAR,
        pod_id VARCHAR,
        factor VARCHAR,
        sample_size INTEGER,
        hit_rate DOUBLE,
        avg_forward_return DOUBLE,
        avg_pnl DOUBLE,
        false_positive_rate DOUBLE,
        false_negative_rate DOUBLE,
        confidence DOUBLE,
        last_updated_at VARCHAR,
        PRIMARY KEY (entity_type, entity_id, pod_id, factor)
    )
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        super().__init__(db_path)
        self._conn.execute(self.SCHEMA)

    def update_from_evaluations(self, evaluations: list[dict]) -> dict:
        buckets: dict[tuple[str, str, str, str], list[dict]] = {}
        for ev in evaluations or []:
            pod_id = str(ev.get("pod_id") or "")
            symbol = str(ev.get("symbol") or "").upper()
            if symbol:
                buckets.setdefault(("symbol", symbol, pod_id, ""), []).append(ev)
            side = str(ev.get("side") or "HOLD").upper()
            buckets.setdefault(("decision_side", side, pod_id, ""), []).append(ev)
            for note in ev.get("notes") or []:
                if str(note).startswith("factor:"):
                    buckets.setdefault(("factor", str(note).split(":", 1)[1], pod_id, str(note).split(":", 1)[1]), []).append(ev)
        updated = 0
        for key, rows in buckets.items():
            scores = [float(r.get("score") or 0.5) for r in rows]
            pnls = [float(r.get("pnl") or 0.0) for r in rows]
            rets = [float(r.get("return_pct") or r.get("pnl_pct") or 0.0) for r in rows]
            hit_rate = sum(1 for s in scores if s >= 0.6) / len(scores) if scores else 0.0
            confidence = min(1.0, max(0.1, len(scores) / 20.0))
            self.add_score({
                "entity_type": key[0],
                "entity_id": key[1],
                "pod_id": key[2],
                "factor": key[3],
                "sample_size": len(scores),
                "hit_rate": hit_rate,
                "avg_forward_return": sum(rets) / len(rets) if rets else 0.0,
                "avg_pnl": sum(pnls) / len(pnls) if pnls else 0.0,
                "false_positive_rate": sum(1 for s in scores if s <= 0.35) / len(scores) if scores else 0.0,
                "false_negative_rate": 0.0,
                "confidence": confidence,
            })
            updated += 1
        return {"generated_at": iso_now(), "updated_count": updated}

    def add_score(self, score: dict) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO calibration_scores VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                score.get("entity_type") or "",
                score.get("entity_id") or "",
                score.get("pod_id") or "",
                score.get("factor") or "",
                int(score.get("sample_size") or 0),
                float(score.get("hit_rate") or 0.0),
                float(score.get("avg_forward_return") or 0.0),
                float(score.get("avg_pnl") or 0.0),
                float(score.get("false_positive_rate") or 0.0),
                float(score.get("false_negative_rate") or 0.0),
                float(score.get("confidence") or 0.5),
                score.get("last_updated_at") or iso_now(),
            ],
        )

    def list_scores(self, *, limit: int = 100, entity_type: str | None = None, pod_id: str | None = None) -> list[dict]:
        clauses: list[str] = []
        params: list[Any] = []
        if entity_type:
            clauses.append("entity_type=?")
            params.append(entity_type)
        if pod_id:
            clauses.append("pod_id=?")
            params.append(pod_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        limit = max(1, min(int(limit or 100), 1000))
        rows = self._conn.execute(
            f"SELECT * FROM calibration_scores {where} ORDER BY confidence DESC, sample_size DESC LIMIT ?",
            params + [limit],
        ).fetchall()
        cols = [d[0] for d in self._conn.description] if self._conn.description else []
        return [dict(zip(cols, row)) for row in rows]


class ManagedRuntime:
    """Convenience container for managed-agent operating-layer stores."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self.db_path = db_path
        paths = self._store_paths(db_path)
        self.agent_runs = AgentRunStore(paths["agent_runs"])
        self.artifacts = ArtifactRegistry(paths["artifacts"])
        self.reports = ReportStore(paths["reports"])
        self.budgets = BudgetTracker(paths["budgets"])
        self.scheduler = SchedulerJobRegistry(paths["scheduler"])
        self.decisions = DecisionReplayStore(paths["decisions"], reports=self.reports)
        self.portfolio_construction = PortfolioConstructionStore(paths["portfolio_construction"], reports=self.reports)
        self.thesis_monitor = ThesisMonitorStore(paths["thesis_monitor"], reports=self.reports)
        self.calibration = CalibrationStore(paths["calibration"])
        self.hindsight = HindsightService(self.reports)

    @staticmethod
    def _store_paths(db_path: str) -> dict[str, str]:
        if db_path == ":memory:":
            return {name: ":memory:" for name in (
                "agent_runs",
                "artifacts",
                "reports",
                "budgets",
                "scheduler",
                "decisions",
                "portfolio_construction",
                "thesis_monitor",
                "calibration",
            )}
        base = Path(db_path)
        if base.suffix.lower() == ".duckdb":
            root = base.with_suffix("")
            return {
                "agent_runs": str(root.parent / f"{root.name}_agent_runs.duckdb"),
                "artifacts": str(root.parent / f"{root.name}_artifacts.duckdb"),
                "reports": str(root.parent / f"{root.name}_reports.duckdb"),
                "budgets": str(root.parent / f"{root.name}_budgets.duckdb"),
                "scheduler": str(root.parent / f"{root.name}_scheduler.duckdb"),
                "decisions": str(root.parent / f"{root.name}_decisions.duckdb"),
                "portfolio_construction": str(root.parent / f"{root.name}_portfolio_construction.duckdb"),
                "thesis_monitor": str(root.parent / f"{root.name}_thesis_monitor.duckdb"),
                "calibration": str(root.parent / f"{root.name}_calibration.duckdb"),
            }
        base.mkdir(parents=True, exist_ok=True)
        return {
            "agent_runs": str(base / "agent_runs.duckdb"),
            "artifacts": str(base / "artifacts.duckdb"),
            "reports": str(base / "reports.duckdb"),
            "budgets": str(base / "budgets.duckdb"),
            "scheduler": str(base / "scheduler.duckdb"),
            "decisions": str(base / "decisions.duckdb"),
            "portfolio_construction": str(base / "portfolio_construction.duckdb"),
            "thesis_monitor": str(base / "thesis_monitor.duckdb"),
            "calibration": str(base / "calibration.duckdb"),
        }

    def close(self) -> None:
        for store in (
            self.agent_runs,
            self.artifacts,
            self.reports,
            self.budgets,
            self.scheduler,
            self.decisions,
            self.portfolio_construction,
            self.thesis_monitor,
            self.calibration,
        ):
            store.close()

    def overview(self) -> dict:
        return {
            "generated_at": iso_now(),
            "agent_runs": self.agent_runs.summary(limit=200),
            "artifacts": self.artifacts.summary(),
            "reports": self.reports.summary(),
            "budgets": self.budgets.summary(),
            "scheduler": self.scheduler.summary(),
            "decision_evaluations": {"recent": self.decisions.list_evaluations(limit=50)},
            "portfolio_construction": {"recent": self.portfolio_construction.list_reviews(limit=50)},
            "thesis_monitor": {"recent": self.thesis_monitor.list_results(limit=50)},
            "calibration": {"recent": self.calibration.list_scores(limit=50)},
        }
