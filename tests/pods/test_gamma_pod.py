from __future__ import annotations
from datetime import date, datetime, timezone
import pytest
from src.core.bus.event_bus import EventBus
from src.core.models.market import Bar
from src.core.models.config import (
    PodConfig, RiskBudget, ExecutionConfig, BacktestConfig,
)
from src.core.models.enums import TimeHorizon, AgentType
from src.pods.base.gateway import PodGateway
from src.pods.base.namespace import PodNamespace
from src.pods.runtime.pod_runtime import PodRuntime
from src.pods.templates.gamma.researcher import GammaResearcher
from src.pods.templates.gamma.signal_agent import GammaSignalAgent
from src.pods.templates.gamma.pm_agent import GammaPMAgent
from src.pods.templates.gamma.risk_agent import GammaRiskAgent
from src.pods.templates.gamma.execution_trader import GammaExecutionTrader
from src.pods.templates.gamma.ops_agent import GammaOpsAgent


def _gamma_config(pod_id: str = "gamma") -> PodConfig:
    return PodConfig(
        pod_id=pod_id,
        name="Pod Gamma",
        strategy_family="global_macro",
        universe=["SPY", "TLT", "GLD", "UUP", "EEM"],
        time_horizon=TimeHorizon.MONTHLY,
        risk_budget=RiskBudget(
            target_vol=0.10,
            max_leverage=1.2,
            max_drawdown=0.12,
            max_concentration=0.30,
            max_sector_exposure=0.50,
            liquidity_min_adv_pct=0.01,
            var_limit_95=0.02,
            es_limit_95=0.03,
        ),
        execution=ExecutionConfig(
            style="passive",
            max_participation_rate=0.10,
            allowed_venues=["paper"],
            order_types=["market"],
        ),
        backtest=BacktestConfig(
            start_date=date(2024, 1, 2),
            end_date=date(2024, 6, 30),
            min_history_days=60,
            walk_forward_folds=1,
            latency_ms=0,
            tcm_bps=5.0,
            slippage_model="fixed",
        ),
        pm_agent_type=AgentType.RULE_BASED,
    )


def _bar(close=200.0):
    return Bar(
        symbol="SPY",
        open=close * 0.99,
        high=close * 1.01,
        low=close * 0.98,
        close=close,
        volume=5_000_000,
        timestamp=datetime.now(timezone.utc),
        source="test",
    )


def _make_runtime(pod_id="gamma"):
    bus = EventBus()
    ns = PodNamespace(pod_id)
    config = _gamma_config(pod_id)
    gw = PodGateway(pod_id, bus, config)
    rt = PodRuntime(pod_id, ns, gw, bus)
    rt.set_agents(
        researcher=GammaResearcher("researcher.gamma", pod_id, ns, bus),
        signal=GammaSignalAgent("signal.gamma", pod_id, ns, bus),
        pm=GammaPMAgent("pm.gamma", pod_id, ns, bus),
        risk=GammaRiskAgent("risk.gamma", pod_id, ns, bus),
        exec_trader=GammaExecutionTrader("exec.gamma", pod_id, ns, bus),
        ops=GammaOpsAgent("ops.gamma", pod_id, ns, bus),
    )
    return rt, ns


async def test_gamma_runs_without_error():
    rt, ns = _make_runtime()
    for i in range(5):
        await rt.run_cycle(_bar(200.0 + i))
    assert ns.get("last_heartbeat") is not None


async def test_gamma_signal_computes_macro_score():
    rt, ns = _make_runtime()
    for i in range(25):
        await rt.run_cycle(_bar(200.0 + i))
    assert ns.get("macro_score") is not None


async def test_gamma_risk_approves_small_order():
    from src.core.models.execution import Order
    from src.core.models.enums import Side, OrderType

    bus = EventBus()
    ns = PodNamespace("gamma2")
    risk = GammaRiskAgent("risk.gamma2", "gamma2", ns, bus)
    order = Order(
        pod_id="gamma2",
        symbol="SPY",
        side=Side.BUY,
        order_type=OrderType.MARKET,
        quantity=10.0,
        limit_price=None,
        timestamp=datetime.now(timezone.utc),
        strategy_tag="macro_momentum_SPY",
    )
    out = await risk.run_cycle({"order": order})
    assert out.get("token") is not None


async def test_gamma_pm_fallback_returns_order_or_hold():
    bus = EventBus()
    ns = PodNamespace("gamma3")
    pm = GammaPMAgent("pm.gamma3", "gamma3", ns, bus)
    bar = _bar(200.0)
    out = await pm.run_cycle({"bar": bar, "macro_score": 0.05})
    # Either an order or empty dict (hold) — both are valid
    assert "order" in out or out == {}


async def test_gamma_ops_heartbeat():
    bus = EventBus()
    ns = PodNamespace("gamma4")
    ops = GammaOpsAgent("ops.gamma4", "gamma4", ns, bus)
    out = await ops.run_cycle({})
    assert out["heartbeat_ok"] is True
