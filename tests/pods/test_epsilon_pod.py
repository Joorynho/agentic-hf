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
from src.pods.templates.epsilon.researcher import EpsilonResearcher
from src.pods.templates.epsilon.signal_agent import EpsilonSignalAgent
from src.pods.templates.epsilon.pm_agent import EpsilonPMAgent
from src.pods.templates.epsilon.risk_agent import EpsilonRiskAgent
from src.pods.templates.epsilon.execution_trader import EpsilonExecutionTrader
from src.pods.templates.epsilon.ops_agent import EpsilonOpsAgent


def _epsilon_config():
    return PodConfig(
        pod_id="epsilon", name="Epsilon", strategy_family="vol_regime",
        universe=["VXX", "SVXY", "SPY"],
        time_horizon=TimeHorizon.SWING,
        risk_budget=RiskBudget(target_vol=0.10, max_leverage=1.5, max_drawdown=0.09,
            max_concentration=0.5, max_sector_exposure=1.0,
            liquidity_min_adv_pct=0.01, var_limit_95=0.02, es_limit_95=0.025),
        execution=ExecutionConfig(style="neutral", max_participation_rate=0.1,
            allowed_venues=["nyse"], order_types=["market"]),
        backtest=BacktestConfig(start_date=date(2024,1,1), end_date=date(2024,12,31),
            min_history_days=30, walk_forward_folds=1, latency_ms=50, tcm_bps=5.0,
            slippage_model="sqrt_impact"),
        pm_agent_type=AgentType.RULE_BASED,
    )


def _bar(close=100.0):
    return Bar(symbol="VXX", timestamp=datetime.now(timezone.utc),
               open=close*0.99, high=close*1.01, low=close*0.98,
               close=close, volume=2_000_000, source="test")


def _make_runtime(pod_id="epsilon"):
    bus = EventBus()
    ns = PodNamespace(pod_id)
    cfg = _epsilon_config()
    gw = PodGateway(pod_id, bus, cfg)
    rt = PodRuntime(pod_id, ns, gw, bus)
    rt.set_agents(
        researcher=EpsilonResearcher("researcher.epsilon", pod_id, ns, bus),
        signal=EpsilonSignalAgent("signal.epsilon", pod_id, ns, bus),
        pm=EpsilonPMAgent("pm.epsilon", pod_id, ns, bus),
        risk=EpsilonRiskAgent("risk.epsilon", pod_id, ns, bus),
        exec_trader=EpsilonExecutionTrader("exec.epsilon", pod_id, ns, bus),
        ops=EpsilonOpsAgent("ops.epsilon", pod_id, ns, bus),
    )
    return rt, ns


async def test_epsilon_runs_without_error():
    rt, ns = _make_runtime()
    for i in range(5):
        await rt.run_cycle(_bar(100.0 + i))
    assert ns.get("last_heartbeat") is not None


async def test_epsilon_signal_classifies_all_regimes():
    from src.pods.templates.epsilon.signal_agent import EpsilonSignalAgent
    bus = EventBus()
    ns = PodNamespace("eps_sig")
    sig = EpsilonSignalAgent("sig.eps", "eps_sig", ns, bus)

    cases = [(10.0, "low"), (20.0, "normal"), (30.0, "high"), (40.0, "extreme")]
    for vix, expected in cases:
        out = await sig.run_cycle({"vix_level": vix, "front_back_ratio": 0.95})
        assert out["regime"] == expected, f"VIX={vix} expected {expected}, got {out['regime']}"


async def test_epsilon_pm_trades_on_regime_change():
    from src.pods.templates.epsilon.pm_agent import EpsilonPMAgent
    bus = EventBus()
    ns = PodNamespace("eps_pm")
    pm = EpsilonPMAgent("pm.eps", "eps_pm", ns, bus)

    # First cycle: low regime -> should buy SVXY
    out = await pm.run_cycle({"bar": _bar(), "regime": "low"})
    assert out.get("order") is not None
    assert out["order"].symbol == "SVXY"


async def test_epsilon_risk_approves_normal_order():
    from src.pods.templates.epsilon.risk_agent import EpsilonRiskAgent
    from src.core.models.execution import Order
    from src.core.models.enums import Side, OrderType
    bus = EventBus()
    ns = PodNamespace("eps_risk")
    risk = EpsilonRiskAgent("risk.eps", "eps_risk", ns, bus)
    order = Order(pod_id="eps_risk", symbol="VXX", side=Side.BUY,
                  order_type=OrderType.MARKET, quantity=50.0,
                  limit_price=None, timestamp=datetime.now(timezone.utc),
                  strategy_tag="vol_regime_high")
    out = await risk.run_cycle({"order": order})
    assert out.get("token") is not None
    assert out["token"].is_valid()


async def test_epsilon_ops_detects_stale_vix():
    from src.pods.templates.epsilon.ops_agent import EpsilonOpsAgent
    bus = EventBus()
    ns = PodNamespace("eps_ops")
    ops = EpsilonOpsAgent("ops.eps", "eps_ops", ns, bus)
    # No VIX stored -- should flag as not fresh
    out = await ops.run_cycle({})
    assert out["heartbeat_ok"] is True
    assert out["vix_fresh"] is False
