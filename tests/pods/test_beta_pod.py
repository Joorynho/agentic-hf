from __future__ import annotations
from datetime import date, datetime, timezone
import pytest

from src.core.bus.event_bus import EventBus
from src.core.models.config import (
    BacktestConfig, ExecutionConfig, PodConfig, RiskBudget,
)
from src.core.models.enums import AgentType, TimeHorizon, Side, OrderType
from src.core.models.execution import Order
from src.core.models.market import Bar
from src.pods.base.gateway import PodGateway
from src.pods.base.namespace import PodNamespace
from src.pods.runtime.pod_runtime import PodRuntime
from src.pods.templates.beta.researcher import BetaResearcher
from src.pods.templates.beta.signal_agent import BetaSignalAgent
from src.pods.templates.beta.pm_agent import BetaPMAgent
from src.pods.templates.beta.risk_agent import BetaRiskAgent
from src.pods.templates.beta.execution_trader import BetaExecutionTrader
from src.pods.templates.beta.ops_agent import BetaOpsAgent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pod_config(pod_id: str = "beta") -> PodConfig:
    return PodConfig(
        pod_id=pod_id,
        name="Beta Stat-Arb",
        strategy_family="stat_arb",
        universe=["XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU"],
        time_horizon=TimeHorizon.SWING,
        risk_budget=RiskBudget(
            target_vol=0.10,
            max_leverage=2.0,
            max_drawdown=0.15,
            max_concentration=0.25,
            max_sector_exposure=0.40,
            liquidity_min_adv_pct=0.01,
            var_limit_95=0.05,
            es_limit_95=0.07,
        ),
        execution=ExecutionConfig(
            style="neutral",
            max_participation_rate=0.10,
            allowed_venues=["paper"],
            order_types=["market"],
        ),
        backtest=BacktestConfig(
            start_date=date(2023, 1, 1),
            end_date=date(2024, 1, 1),
            min_history_days=60,
            walk_forward_folds=1,
            latency_ms=0,
            tcm_bps=5.0,
            slippage_model="fixed",
        ),
        pm_agent_type=AgentType.RULE_BASED,
    )


def _make_runtime(pod_id: str = "beta"):
    bus = EventBus()
    ns = PodNamespace(pod_id)
    gw = PodGateway(pod_id, bus, _make_pod_config(pod_id))
    runner = PodRuntime(pod_id, ns, gw, bus)
    runner.set_agents(
        researcher=BetaResearcher("researcher.beta", pod_id, ns, bus),
        signal=BetaSignalAgent("signal.beta", pod_id, ns, bus),
        pm=BetaPMAgent("pm.beta", pod_id, ns, bus),
        risk=BetaRiskAgent("risk.beta", pod_id, ns, bus),
        exec_trader=BetaExecutionTrader("exec.beta", pod_id, ns, bus),
        ops=BetaOpsAgent("ops.beta", pod_id, ns, bus),
    )
    return runner, ns


def _bar(close: float = 100.0) -> Bar:
    return Bar(
        symbol="XLK",
        open=close * 0.99,
        high=close * 1.01,
        low=close * 0.98,
        close=close,
        volume=1_000_000,
        timestamp=datetime.now(timezone.utc),
        source="test",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

async def test_beta_runtime_runs_without_error():
    """Full pipeline runs 10 bars without raising."""
    runner, ns = _make_runtime()
    for i in range(10):
        await runner.run_cycle(_bar(100.0 + i))
    assert ns.get("researcher_ok") is True
    assert ns.get("last_heartbeat") is not None


async def test_beta_signal_zscore_stored():
    """After enough bars, latest_signals is populated with pair z-scores."""
    runner, ns = _make_runtime()
    for i in range(10):
        await runner.run_cycle(_bar(100.0))
    signals = ns.get("latest_signals")
    assert signals is not None
    assert "XLK_XLF" in signals


async def test_beta_pm_entry_on_high_zscore():
    """PM proposes an entry order when a pair z-score exceeds ENTRY_Z."""
    bus = EventBus()
    ns = PodNamespace("beta_pm")
    pm = BetaPMAgent("pm.beta_pm", "beta_pm", ns, bus)

    # Force a signal above entry threshold
    signals = {"XLK_XLF": 2.5}
    ns.set("latest_signals", signals)
    out = await pm.run_cycle({"bar": _bar(100.0), "signals": signals})
    assert out.get("order") is not None


async def test_beta_risk_approves_small_order():
    """Risk agent approves an order well within exposure limits."""
    bus = EventBus()
    ns = PodNamespace("beta_risk")
    risk = BetaRiskAgent("risk.beta_risk", "beta_risk", ns, bus)

    order = Order(
        pod_id="beta_risk",
        symbol="XLK",
        side=Side.BUY,
        order_type=OrderType.MARKET,
        quantity=10.0,
        limit_price=None,
        timestamp=datetime.now(timezone.utc),
        strategy_tag="entry_XLK_XLF",
    )
    out = await risk.run_cycle({"order": order})
    assert out.get("token") is not None
    assert out["token"].is_valid()


async def test_beta_ops_heartbeat():
    """Ops agent writes a heartbeat on every cycle."""
    bus = EventBus()
    ns = PodNamespace("beta_ops")
    ops = BetaOpsAgent("ops.beta_ops", "beta_ops", ns, bus)
    out = await ops.run_cycle({})
    assert out["heartbeat_ok"] is True
    assert "ts" in out
