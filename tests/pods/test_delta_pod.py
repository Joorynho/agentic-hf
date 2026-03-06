from __future__ import annotations
from datetime import date, datetime, timezone
import pytest
from src.core.bus.event_bus import EventBus
from src.core.models.config import PodConfig, RiskBudget, ExecutionConfig, BacktestConfig
from src.core.models.enums import AgentType, TimeHorizon
from src.core.models.market import Bar
from src.pods.base.gateway import PodGateway
from src.pods.base.namespace import PodNamespace
from src.pods.runtime.pod_runtime import PodRuntime
from src.pods.templates.delta.researcher import DeltaResearcher
from src.pods.templates.delta.signal_agent import DeltaSignalAgent
from src.pods.templates.delta.pm_agent import DeltaPMAgent
from src.pods.templates.delta.risk_agent import DeltaRiskAgent
from src.pods.templates.delta.execution_trader import DeltaExecutionTrader
from src.pods.templates.delta.ops_agent import DeltaOpsAgent


def _delta_config():
    return PodConfig(
        pod_id="delta", name="Delta", strategy_family="event_driven",
        universe=["AAPL","MSFT","AMZN","GOOGL","META"],
        time_horizon=TimeHorizon.SWING,
        risk_budget=RiskBudget(target_vol=0.15, max_leverage=1.0, max_drawdown=0.12,
            max_concentration=0.05, max_sector_exposure=0.3,
            liquidity_min_adv_pct=0.01, var_limit_95=0.02, es_limit_95=0.025),
        execution=ExecutionConfig(style="neutral", max_participation_rate=0.1,
            allowed_venues=["nasdaq"], order_types=["market","limit"]),
        backtest=BacktestConfig(start_date=date(2024,1,1), end_date=date(2024,12,31),
            min_history_days=30, walk_forward_folds=1, latency_ms=100, tcm_bps=5.0,
            slippage_model="sqrt_impact"),
        pm_agent_type=AgentType.LLM_ASSISTED,
    )


def _bar(close=150.0, ts_offset=0):
    from datetime import timedelta
    ts = datetime(2024, 1, 1, 9, 30, tzinfo=timezone.utc) + timedelta(days=ts_offset)
    return Bar(symbol="AAPL", timestamp=ts, open=close*0.99, high=close*1.01,
               low=close*0.98, close=close, volume=1_000_000, source="test")


def _make_runtime(pod_id="delta"):
    bus = EventBus()
    ns = PodNamespace(pod_id)
    cfg = _delta_config()
    gw = PodGateway(pod_id, bus, cfg)
    rt = PodRuntime(pod_id, ns, gw, bus)
    rt.set_agents(
        researcher=DeltaResearcher("researcher.delta", pod_id, ns, bus),
        signal=DeltaSignalAgent("signal.delta", pod_id, ns, bus),
        pm=DeltaPMAgent("pm.delta", pod_id, ns, bus),
        risk=DeltaRiskAgent("risk.delta", pod_id, ns, bus),
        exec_trader=DeltaExecutionTrader("exec.delta", pod_id, ns, bus),
        ops=DeltaOpsAgent("ops.delta", pod_id, ns, bus),
    )
    return rt, ns


async def test_delta_runs_without_error():
    rt, ns = _make_runtime()
    for i in range(5):
        await rt.run_cycle(_bar(150.0, ts_offset=i))
    assert ns.get("last_heartbeat") is not None


async def test_delta_signal_computes_composite():
    rt, ns = _make_runtime()
    for i in range(3):
        await rt.run_cycle(_bar(150.0, ts_offset=i))
    score = ns.get("composite_score")
    assert score is not None
    assert 0.0 <= score <= 1.0


async def test_delta_pm_auto_expiry():
    """After MAX_HOLD_BARS, PM should close position."""
    from src.pods.templates.delta.pm_agent import DeltaPMAgent, MAX_HOLD_BARS
    bus = EventBus()
    ns = PodNamespace("delta_exp")
    pm = DeltaPMAgent("pm.delta_exp", "delta_exp", ns, bus)

    # Simulate active position near expiry
    ns.set("active_position", True)
    ns.set("hold_bars", MAX_HOLD_BARS - 1)
    ns.set("composite_score", 0.0)

    out = await pm.run_cycle({"bar": _bar(), "composite_score": 0.0})
    assert out.get("order") is not None
    assert out["order"].strategy_tag == "delta_auto_expiry"


async def test_delta_risk_approves_small_order():
    from src.pods.templates.delta.risk_agent import DeltaRiskAgent
    from src.core.models.execution import Order
    from src.core.models.enums import Side, OrderType
    bus = EventBus()
    ns = PodNamespace("delta_risk")
    risk = DeltaRiskAgent("risk.delta_risk", "delta_risk", ns, bus)
    order = Order(pod_id="delta_risk", symbol="AAPL", side=Side.BUY,
                  order_type=OrderType.MARKET, quantity=5.0,
                  limit_price=None, timestamp=datetime.now(timezone.utc),
                  strategy_tag="delta_event_0.80")
    out = await risk.run_cycle({"order": order})
    assert out.get("token") is not None
    assert out["token"].is_valid()


async def test_delta_ops_heartbeat():
    from src.pods.templates.delta.ops_agent import DeltaOpsAgent
    bus = EventBus()
    ns = PodNamespace("delta_ops")
    ops = DeltaOpsAgent("ops.delta_ops", "delta_ops", ns, bus)
    out = await ops.run_cycle({})
    assert out["heartbeat_ok"] is True
