"""Tests for all core data models (Tasks 2-5)."""

import time as t
from datetime import datetime
from uuid import uuid4

import pytest

from src.core.models.enums import (
    AgentType,
    AlertSeverity,
    EventType,
    OrderType,
    PodStatus,
    Side,
    TimeHorizon,
)
from src.core.models.messages import AgentMessage, Event
from src.core.models.config import (
    BacktestConfig,
    ExecutionConfig,
    PodConfig,
    RiskBudget,
)
from src.core.models.market import Bar, NewsItem
from src.core.models.execution import (
    Fill,
    Order,
    Position,
    RejectedOrder,
    RiskApprovalToken,
)
from src.core.models.pod_summary import (
    PodExposureBucket,
    PodRiskMetrics,
    PodSummary,
)


# ── Task 2: Enums and AgentMessage ──────────────────────────────────────────


def test_agent_message_serializes_to_json():
    msg = AgentMessage(
        id=uuid4(),
        timestamp="2024-01-01T09:30:00",
        sender="risk_manager",
        recipient="pod.alpha.gateway",
        topic="governance.alpha",
        payload={"action": "halt"},
        correlation_id=None,
    )
    data = msg.model_dump_json()
    assert "risk_manager" in data
    assert "governance.alpha" in data


def test_event_type_has_required_values():
    assert EventType.MARKET_DATA
    assert EventType.NEWS
    assert EventType.RISK_BREACH
    assert EventType.KILL_SWITCH
    assert EventType.ALLOCATION_CHANGE
    assert EventType.POD_STARTED
    assert EventType.POD_HALTED


# ── Task 3: Pod Config and Risk Budget ──────────────────────────────────────


def test_pod_config_validates_risk_budget():
    cfg = PodConfig(
        pod_id="alpha",
        name="Pod Alpha",
        strategy_family="momentum",
        universe=["AAPL", "MSFT", "GOOGL"],
        time_horizon=TimeHorizon.SWING,
        risk_budget=RiskBudget(
            target_vol=0.12,
            max_leverage=1.5,
            max_drawdown=0.10,
            max_concentration=0.05,
            max_sector_exposure=0.30,
            liquidity_min_adv_pct=0.01,
            var_limit_95=0.02,
            es_limit_95=0.03,
        ),
        execution=ExecutionConfig(
            style="passive",
            max_participation_rate=0.10,
            allowed_venues=["paper"],
            order_types=["market", "limit"],
        ),
        backtest=BacktestConfig(
            start_date="2020-01-01",
            end_date="2023-12-31",
            min_history_days=252,
            walk_forward_folds=3,
            latency_ms=100,
            tcm_bps=5.0,
            slippage_model="sqrt_impact",
        ),
        pm_agent_type=AgentType.RULE_BASED,
    )
    assert cfg.pod_id == "alpha"
    assert cfg.risk_budget.target_vol == 0.12


def test_risk_budget_rejects_invalid_vol():
    with pytest.raises(Exception):
        RiskBudget(
            target_vol=2.0,
            max_leverage=1.5,
            max_drawdown=0.10,
            max_concentration=0.05,
            max_sector_exposure=0.30,
            liquidity_min_adv_pct=0.01,
            var_limit_95=0.02,
            es_limit_95=0.03,
        )


# ── Task 4: Market Data and Execution ───────────────────────────────────────


def test_bar_model():
    bar = Bar(
        symbol="AAPL",
        timestamp=datetime(2024, 1, 2, 9, 30),
        open=185.0,
        high=186.5,
        low=184.2,
        close=186.0,
        volume=50_000_000,
        adj_close=186.0,
        source="yfinance",
    )
    assert bar.symbol == "AAPL"


def test_order_has_strategy_tag():
    order = Order(
        pod_id="alpha",
        symbol="AAPL",
        side=Side.BUY,
        order_type=OrderType.MARKET,
        quantity=100,
        limit_price=None,
        timestamp=datetime.now(),
        strategy_tag="momentum_cross",
    )
    assert order.strategy_tag == "momentum_cross"


def test_risk_approval_token_expires():
    token = RiskApprovalToken(
        pod_id="alpha",
        order_id=uuid4(),
        expires_ms=50,
    )
    assert token.is_valid()
    t.sleep(0.1)
    assert not token.is_valid()


# ── Task 5: PodSummary ──────────────────────────────────────────────────────


def test_pod_summary_has_no_raw_positions():
    summary = PodSummary(
        pod_id="alpha",
        timestamp=datetime.now(),
        status=PodStatus.ACTIVE,
        risk_metrics=PodRiskMetrics(
            pod_id="alpha",
            timestamp=datetime.now(),
            nav=1_000_000,
            daily_pnl=5000,
            drawdown_from_hwm=-0.01,
            current_vol_ann=0.09,
            gross_leverage=1.2,
            net_leverage=0.8,
            var_95_1d=0.012,
            es_95_1d=0.018,
        ),
        exposure_buckets=[
            PodExposureBucket(
                asset_class="equity_us",
                direction="long",
                notional_pct_nav=0.85,
            )
        ],
        expected_return_estimate=0.12,
        turnover_daily_pct=0.05,
        heartbeat_ok=True,
        error_message=None,
    )
    # Note: "positions" IS now part of PodSummary (Phase 1.3) - it contains aggregated position data from PortfolioAccountant
    assert hasattr(summary, "positions"), "PodSummary should include positions field (Phase 1.3)"
    assert summary.positions == [], "positions should be empty list by default"
    assert not hasattr(summary, "signal_value"), "Must not expose raw signal internals"
    assert summary.pod_id == "alpha"
