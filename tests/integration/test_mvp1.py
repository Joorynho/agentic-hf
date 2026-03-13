import pytest, tempfile, asyncio
from datetime import date, datetime, timedelta
from unittest.mock import patch

# Backtest runner
from src.backtest.engine.backtest_runner import BacktestRunner
from src.core.models.config import PodConfig, RiskBudget, ExecutionConfig, BacktestConfig
from src.core.models.enums import TimeHorizon, AgentType, PodStatus

# Risk manager
from src.agents.risk.risk_manager import RiskManager
from src.core.bus.event_bus import EventBus
from src.core.bus.audit_log import AuditLog
from src.core.models.pod_summary import PodSummary, PodRiskMetrics, PodExposureBucket

# Pod isolation
from src.pods.base.namespace import PodNamespace
from src.core.bus.exceptions import TopicAccessError
from src.core.models.messages import AgentMessage

# Alpha PM
from src.pods.templates.alpha.momentum_pm import MomentumPMAgent
from src.core.models.market import Bar


def make_alpha_config():
    return PodConfig(
        pod_id="alpha", name="Pod Alpha", strategy_family="momentum",
        universe=["AAPL", "MSFT"],
        time_horizon=TimeHorizon.SWING,
        risk_budget=RiskBudget(
            target_vol=0.12, max_leverage=1.5, max_drawdown=0.10,
            max_concentration=0.05, max_sector_exposure=0.30,
            liquidity_min_adv_pct=0.01, var_limit_95=0.02, es_limit_95=0.03),
        execution=ExecutionConfig(
            style="passive", max_participation_rate=0.10,
            allowed_venues=["paper"], order_types=["market"]),
        backtest=BacktestConfig(
            start_date=date(2024, 1, 2), end_date=date(2024, 3, 31),
            min_history_days=10, walk_forward_folds=1,
            latency_ms=0, tcm_bps=5.0, slippage_model="fixed"),
        pm_agent_type=AgentType.RULE_BASED)


def _fake_bars(symbol, start, end):
    bars = []
    current = datetime.combine(start, datetime.min.time())
    end_dt = datetime.combine(end, datetime.min.time())
    price = 180.0 if symbol == "AAPL" else 350.0
    day = 0
    while current < end_dt:
        if current.weekday() < 5:
            p = price + day * 0.5
            bars.append(Bar(
                symbol=symbol, timestamp=current,
                open=p, high=p + 2, low=p - 1, close=p + 1,
                volume=1_000_000, source="test",
            ))
            day += 1
        current += timedelta(days=1)
    return bars


@pytest.mark.asyncio
async def test_mvp1_backtest_full_run():
    """Full backtest run: data fetch + replay + accounting."""
    cache_dir = tempfile.mkdtemp()
    with patch(
        "src.data.adapters.yfinance_adapter.YFinanceAdapter._fetch_sync",
        side_effect=lambda sym, s, e: _fake_bars(sym, s, e),
    ):
        result = await BacktestRunner(cache_dir=cache_dir).run(make_alpha_config())
    assert result["total_bars_processed"] > 0
    assert result["nav_final"] > 0
    assert result["pod_id"] == "alpha"


@pytest.mark.asyncio
async def test_mvp1_risk_manager_integration():
    """Risk manager checks a pod summary and triggers halt on breach."""
    bus = EventBus(audit_log=AuditLog())
    rm = RiskManager(bus=bus)
    halted = []

    async def on_alert(msg):
        if msg.payload.get("action") == "halt":
            halted.append(msg.payload["pod_id"])

    await bus.subscribe("risk.alert", on_alert)

    # Summary with drawdown breach (-0.15 exceeds -0.10 limit)
    summary = PodSummary(
        pod_id="alpha", timestamp=datetime.now(), status=PodStatus.ACTIVE,
        risk_metrics=PodRiskMetrics(
            pod_id="alpha", timestamp=datetime.now(), nav=900_000,
            daily_pnl=-50000, drawdown_from_hwm=-0.15,
            current_vol_ann=0.09, gross_leverage=1.2, net_leverage=0.8,
            var_95_1d=0.01, es_95_1d=0.015),
        exposure_buckets=[], expected_return_estimate=0.10,
        turnover_daily_pct=0.02, heartbeat_ok=True)
    budget = make_alpha_config().risk_budget
    breaches = await rm.check_pod(summary, budget)
    await asyncio.sleep(0.05)
    assert len(breaches) > 0
    assert "alpha" in halted


def test_mvp1_isolation_namespace():
    """Pods cannot read each other's namespace."""
    ns_a = PodNamespace("alpha")
    ns_b = PodNamespace("beta")
    ns_a.set("secret_signal", 42)
    assert ns_b.get("secret_signal") is None
    assert ns_a.get("secret_signal") == 42


@pytest.mark.asyncio
async def test_mvp1_isolation_bus():
    """Pods cannot publish to sibling gateways."""
    bus = EventBus()
    msg = AgentMessage(timestamp=datetime.now(), sender="pod.alpha",
                       recipient="pod.beta", topic="pod.beta.gateway", payload={})
    with pytest.raises(TopicAccessError):
        await bus.publish("pod.beta.gateway", msg, publisher_id="pod.alpha")


def test_mvp1_alpha_pm_signal():
    """Alpha pod PM generates valid momentum signal."""
    ns = PodNamespace("alpha")
    pm = MomentumPMAgent(pod_id="alpha", namespace=ns, fast_window=3, slow_window=5)
    # Uptrend
    bars = [Bar(symbol="AAPL", timestamp=datetime(2024, 1, i + 1),
                open=100 + i, high=101 + i, low=99 + i, close=100 + i,
                volume=1_000_000, source="test") for i in range(7)]
    signal = pm.compute_signal("AAPL", bars)
    assert signal > 0
    assert ns.get("signal::AAPL") == signal
