# Current Task - Agentic HF V3 Decision Evaluation + Portfolio Construction

Goal: implement V3 incrementally on top of the V2 catalyst/managed-runtime layer. V3 adds decision snapshots, lightweight evaluation, dry-run shadow replay, factor-aware opportunity mapping, an advisory portfolio-construction gate, live thesis monitoring, calibration scores, and clearer model-router metadata.

## Implementation Checklist

- [x] Add V3 models and durable stores for decision snapshots, evaluations, shadow replay, portfolio construction, thesis monitoring, calibration, and instrument profiles.
- [x] Persist sanitized decision snapshots for all final PM decisions, including HOLD paths where available.
- [x] Add lightweight decision evaluation and report output after horizons expire.
- [x] Add dry-run shadow replay that cannot submit orders or mutate live pod state.
- [x] Upgrade factor exposure data into an instrument opportunity map.
- [x] Add advisory portfolio-construction review before hard risk/execution gates.
- [x] Add live thesis monitoring for open positions and add-block/review recommendations.
- [x] Add calibration aggregation from evaluations/hindsight into ranking/prompt context only.
- [x] Extend model routing telemetry with model tier, selection reason, budget mode, and fallback path.
- [x] Expose V3 APIs and keep dashboard changes lightweight through existing report/trace surfaces.
- [x] Add focused unit/API/regression tests.
- [x] Run targeted verification and document remaining scope.

## Review

- Added V3 Pydantic models and DuckDB-backed stores for decision snapshots/evaluations, shadow replay, portfolio-construction reviews, thesis-monitor results, calibration scores, and instrument profiles.
- `PodRuntime` now records sanitized final PM decision snapshots, updates snapshot status when gates block or execution returns, injects instrument profiles into PM context, runs live thesis monitoring for open positions, and applies an advisory portfolio-construction gate before IC/risk/execution. The gate can downsize, trim to cash, skip duplicative exposure, or request revision, but cannot increase size or bypass hard controls.
- Added factor-aware `InstrumentProfile` mapping that distinguishes GLD vs GDX, oil ETFs vs energy equities, TLT duration exposure, USD/rate-differential ETFs, and crypto beta/chain-specific exposures.
- Added lightweight decision evaluation, dry-run shadow replay report generation, calibration aggregation, and API endpoints: `/api/decision-evaluations`, `/api/shadow-replay`, `/api/portfolio-construction`, `/api/thesis-monitor`, and `/api/calibration`.
- Extended managed agent/model telemetry with `model_tier`, `model_selection_reason`, `budget_mode`, and `fallback_path`.
- Verification passed for targeted V3/runtime/web coverage: compileall for modified backend files; `tests/unit/test_v3_decision_os.py`; `tests/unit/test_managed_runtime.py`; `tests/unit/test_llm_controls.py`; `tests/unit/test_pre_trade_quality_gate.py`; `tests/unit/test_pod_runtime_entry_thesis.py`; `tests/integration/test_web_service.py`; and the `test_state_health_does_not_block_on_live_broker_fetch` regression.
- Full `pytest tests/ -q --tb=short` reached 679 passed / 2 skipped before reporting 4 failures: three integration tests hit a Windows DuckDB lock on `data/research_feed.duckdb` from another live Python process, and one defensive state-health fake-accountant failure was fixed and re-verified. Pytest also continues to report the existing `.pytest_cache` permission warning on Windows.
