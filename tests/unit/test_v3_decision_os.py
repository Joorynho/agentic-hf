from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from src.core.instrument_profile import get_instrument_profile, profiles_for_catalyst
from src.core.managed_runtime import ManagedRuntime
from src.core.models.enums import OrderType, Side
from src.core.models.execution import Order
from src.core.portfolio_construction import review_portfolio_construction
from src.core.thesis_monitor import monitor_position_thesis


def _order(symbol: str, side: Side = Side.BUY, qty: float = 1.0) -> Order:
    return Order(
        pod_id="commodities",
        symbol=symbol,
        side=side,
        order_type=OrderType.MARKET,
        quantity=qty,
        timestamp=datetime.now(timezone.utc),
        strategy_tag="test",
        conviction=0.7,
    )


def test_decision_snapshot_evaluation_replay_and_calibration(tmp_path):
    runtime = ManagedRuntime(str(tmp_path / "managed_runtime.duckdb"))
    try:
        snapshot_id = runtime.decisions.add_snapshot(
            {
                "pod_id": "crypto",
                "symbol": "SOL/USD",
                "side": "BUY",
                "price_at_decision": 100.0,
                "catalyst_ids": ["cat_sol"],
                "thesis_fields": {"why_now": "alt momentum is broadening"},
                "artifact_status": {"status": "ok"},
            }
        )

        result = runtime.decisions.evaluate_due(
            outcome_context={
                "symbols": {
                    "SOL/USD": {
                        "price": 110.0,
                        "pnl": 10.0,
                        "pnl_pct": 0.10,
                    }
                }
            }
        )
        assert result["created_count"] == 1
        evaluations = runtime.decisions.list_evaluations(symbol="SOL/USD")
        assert evaluations[0]["snapshot_id"] == snapshot_id
        assert evaluations[0]["outcome"] == "supported"

        replay = runtime.decisions.record_shadow_replay(
            snapshot_id,
            {
                "side": "HOLD",
                "symbol": "SOL/USD",
                "reason": "Dry-run degraded dependency policy would hold.",
            },
        )
        assert replay["dry_run"] is True
        assert replay["execution_attempted"] is False
        assert replay["state_mutation_detected"] is False
        assert replay["changed"] is True

        calibration = runtime.calibration.update_from_evaluations(evaluations)
        assert calibration["updated_count"] >= 2
        scores = runtime.calibration.list_scores()
        assert any(score["entity_type"] == "symbol" and score["entity_id"] == "SOL/USD" for score in scores)
    finally:
        runtime.close()


def test_instrument_profiles_distinguish_related_exposures():
    gld = get_instrument_profile("GLD")
    gdx = get_instrument_profile("GDX")
    tlt = get_instrument_profile("TLT")
    usdu = get_instrument_profile("USDU")
    sol = get_instrument_profile("SOL/USD")

    assert gld.primary_factor == "gold_beta"
    assert gdx.primary_factor == "miners_equity"
    assert gdx.factor_loadings["gold_beta"] > 0.5
    assert gdx.factor_loadings["equity_beta"] > 0.0
    assert tlt.primary_factor == "duration"
    assert usdu.primary_factor == "usd"
    assert sol.factor_loadings["crypto_beta"] > 0.5
    assert sol.factor_loadings["onchain_activity"] > 0.5

    profiles = profiles_for_catalyst({"factors": ["gold_beta"], "affected_symbols": ["GLD"]})
    symbols = {row["symbol"] for row in profiles}
    assert {"GLD", "GDX"}.issubset(symbols)


def test_portfolio_construction_detects_duplicate_exposure_and_cash_limits():
    positions = {"GLD": SimpleNamespace(qty=4.0, current_price=100.0)}
    review = review_portfolio_construction(
        pod_id="commodities",
        order=_order("GDX", qty=2.0),
        positions=positions,
        nav=1000.0,
        cash=1000.0,
        fallback_price=100.0,
    )
    assert review.action in {"DOWNSIZE", "SKIP_DUPLICATIVE"}
    assert any("gold_beta" in item or "precious_metals" in item for item in review.duplicate_exposures)

    funded = review_portfolio_construction(
        pod_id="commodities",
        order=_order("GLD", qty=5.0),
        positions={},
        nav=1000.0,
        cash=100.0,
        fallback_price=50.0,
    )
    assert funded.action == "TRIM_TO_FUND"
    assert funded.recommended_notional == 100.0

    reduction = review_portfolio_construction(
        pod_id="commodities",
        order=_order("GLD", side=Side.SELL, qty=1.0),
        positions={"GLD": SimpleNamespace(qty=4.0, current_price=100.0)},
        nav=1000.0,
        cash=50.0,
        fallback_price=100.0,
    )
    assert reduction.action == "APPROVE_SIZE"


def test_thesis_monitor_blocks_expansion_when_catalyst_expired():
    old_entry = (datetime.now(timezone.utc) - timedelta(days=12)).isoformat()
    expired_horizon = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    position = SimpleNamespace(
        entry_thesis="Liquidity regime supports SOL beta, but this thesis needs a catalyst horizon review.",
        entry_date=old_entry,
        max_hold_days=20,
        unrealized_pnl=0.0,
        market_value=100.0,
    )

    result = monitor_position_thesis(
        pod_id="crypto",
        symbol="SOL/USD",
        position=position,
        catalyst_events=[
            {
                "event_id": "cat_sol",
                "status": "active",
                "affected_symbols": ["SOL/USD"],
                "horizon_end": expired_horizon,
            }
        ],
        latest_regime="risk-off",
    )

    assert result.status == "ADD_BLOCKED"
    assert "catalyst_horizon_expired" in result.triggers
