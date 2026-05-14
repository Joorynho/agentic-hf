from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.core.managed_runtime import ManagedRuntime


def test_agent_run_store_records_success_failure_and_restart(tmp_path):
    db_path = str(tmp_path / "managed_runtime.duckdb")
    runtime = ManagedRuntime(db_path)
    run_id = runtime.agent_runs.start_run(
        agent_id="equities.pm",
        agent_type="pm",
        pod_id="equities",
        task="pm_decision",
        input_payload={"secret": "do-not-store"},
    )
    runtime.agent_runs.complete_run(run_id, output_summary={"decision": "HOLD"})
    failed_id = runtime.agent_runs.start_run(agent_id="crypto.pm", agent_type="pm", pod_id="crypto")
    runtime.agent_runs.fail_run(failed_id, "model timeout")
    rows = runtime.agent_runs.list_runs(limit=10)
    runtime.close()

    assert {row["status"] for row in rows} == {"success", "failed"}
    assert all("do-not-store" not in str(row) for row in rows)
    assert any(row["input_hash"] for row in rows)

    reopened = ManagedRuntime(db_path)
    try:
        summary = reopened.agent_runs.summary()
        assert summary["count"] == 2
        assert summary["failed_count"] == 1
    finally:
        reopened.close()


def test_artifact_registry_dependency_checks_and_staleness(tmp_path):
    runtime = ManagedRuntime(str(tmp_path / "managed_runtime.duckdb"))
    try:
        runtime.artifacts.record(
            kind="fresh_prices",
            owner="crypto",
            status="fresh",
            freshness_seconds=60,
        )
        assert runtime.artifacts.check_dependency("fresh_prices", owner="crypto", hard=True)["action"] == "pass"

        expired = datetime.now(timezone.utc) - timedelta(seconds=30)
        runtime.artifacts.record(
            kind="broker_snapshot",
            owner="firm",
            status="fresh",
            created_at=expired - timedelta(minutes=10),
            expires_at=expired,
        )
        check = runtime.artifacts.check_dependency("broker_snapshot", owner="firm", hard=True)
        assert check["action"] == "block"
        assert check["is_expired"] is True

        optional = runtime.artifacts.check_dependency("research_feed", owner="equities", hard=False)
        assert optional["action"] == "degrade"
    finally:
        runtime.close()


def test_report_corpus_filters_and_hindsight_reviews(tmp_path):
    runtime = ManagedRuntime(str(tmp_path / "managed_runtime.duckdb"))
    try:
        old_ts = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        runtime.reports.add_report(
            report_id="pm_1",
            report_type="pm_decision",
            pod_id="crypto",
            symbol="SOL/USD",
            related_catalyst_ids=["cat_sol"],
            title="SOL catch-up trade",
            summary="SOL could benefit if alt momentum broadens; invalidation is a weaker on-chain setup.",
            created_at=old_ts,
        )
        filtered = runtime.reports.list_reports(symbol="SOL/USD", catalyst_id="cat_sol")
        assert len(filtered) == 1
        assert filtered[0]["related_catalyst_ids"] == ["cat_sol"]
        by_factor = runtime.reports.list_reports(factor="alt momentum")
        assert by_factor[0]["report_id"] == "pm_1"
        trace = runtime.reports.decision_trace(symbol="SOL/USD", catalyst_id="cat_sol")
        assert trace["count"] == 1
        assert trace["stages"][0]["stage"] == "pm_decision"

        result = runtime.hindsight.run_once(
            min_age_hours=1,
            outcome_context={"symbols": {"SOL/USD": {"pnl": 12.0, "pnl_pct": 0.04, "updated_recently": True}}},
        )
        assert result["created_count"] == 1
        reviews = runtime.reports.list_reports(report_type="hindsight_review")
        assert reviews
        assert "source_report:pm_1" in reviews[0]["tags"]
        assert any(flag in reviews[0]["quality_flags"] for flag in ("direction_supported", "direction_challenged"))
    finally:
        runtime.close()


def test_budget_tracker_and_scheduler_non_overlap(tmp_path):
    runtime = ManagedRuntime(str(tmp_path / "managed_runtime.duckdb"))
    try:
        runtime.budgets.record_usage(
            task="pm_decision",
            provider="openai",
            model="gpt-5-mini",
            status="success",
            token_estimate=1200,
            cost_estimate=0.003,
        )
        for i in range(runtime.budgets.policy.max_failed_model_calls_before_degraded):
            runtime.budgets.record_usage(
                task="pm_decision",
                provider="openrouter",
                model=f"fallback-{i}",
                status="failed",
                error="rate limited",
            )
        budget = runtime.budgets.summary()
        assert budget["today"]["degraded"] is True
        assert budget["today"]["token_estimate"] >= 1200
        assert budget["today"]["cost_estimate"] >= 0.003

        acquired, _ = runtime.scheduler.start_job("price_refresh", run_id="run_1")
        skipped, state = runtime.scheduler.start_job("price_refresh", run_id="run_2")
        assert acquired is True
        assert skipped is False
        assert state["skipped_count"] == 1
        runtime.scheduler.complete_job("price_refresh")
        jobs = runtime.scheduler.summary()
        assert jobs["running_count"] == 0
    finally:
        runtime.close()
