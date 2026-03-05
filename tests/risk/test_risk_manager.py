import pytest, asyncio
from src.agents.risk.risk_manager import RiskManager
from src.core.bus.event_bus import EventBus
from src.core.models.pod_summary import PodSummary, PodRiskMetrics, PodExposureBucket
from src.core.models.config import RiskBudget
from src.core.models.enums import PodStatus
from datetime import datetime

def make_summary(pod_id, drawdown, vol, leverage, var_1d=0.01):
    return PodSummary(
        pod_id=pod_id, timestamp=datetime.now(), status=PodStatus.ACTIVE,
        risk_metrics=PodRiskMetrics(
            pod_id=pod_id, timestamp=datetime.now(), nav=1_000_000,
            daily_pnl=0, drawdown_from_hwm=drawdown,
            current_vol_ann=vol, gross_leverage=leverage, net_leverage=leverage,
            var_95_1d=var_1d, es_95_1d=0.015),
        exposure_buckets=[],
        expected_return_estimate=0.10,
        turnover_daily_pct=0.02, heartbeat_ok=True)

def make_budget():
    return RiskBudget(
        target_vol=0.12, max_leverage=1.5, max_drawdown=0.10,
        max_concentration=0.05, max_sector_exposure=0.30,
        liquidity_min_adv_pct=0.01, var_limit_95=0.02, es_limit_95=0.03)

@pytest.mark.asyncio
async def test_risk_triggers_halt_on_drawdown_breach():
    bus = EventBus()
    rm = RiskManager(bus=bus)
    halted = []
    async def on_alert(msg):
        if msg.payload.get("action") == "halt":
            halted.append(msg.payload["pod_id"])
    await bus.subscribe("risk.alert", on_alert)
    summary = make_summary("alpha", drawdown=-0.11, vol=0.09, leverage=1.2)
    await rm.check_pod(summary, make_budget())
    await asyncio.sleep(0.05)
    assert "alpha" in halted

@pytest.mark.asyncio
async def test_risk_no_action_within_limits():
    bus = EventBus()
    rm = RiskManager(bus=bus)
    alerts = []
    await bus.subscribe("risk.alert", lambda m: alerts.append(m))
    summary = make_summary("alpha", drawdown=-0.05, vol=0.09, leverage=1.2)
    await rm.check_pod(summary, make_budget())
    await asyncio.sleep(0.05)
    assert len(alerts) == 0

@pytest.mark.asyncio
async def test_risk_triggers_on_leverage_breach():
    bus = EventBus()
    rm = RiskManager(bus=bus)
    alerts = []
    async def on_alert(msg):
        alerts.append(msg)
    await bus.subscribe("risk.alert", on_alert)
    summary = make_summary("beta", drawdown=-0.02, vol=0.08, leverage=2.5)
    breaches = await rm.check_pod(summary, make_budget())
    await asyncio.sleep(0.05)
    assert len(breaches) > 0
    assert "leverage" in breaches[0].lower()

@pytest.mark.asyncio
async def test_firm_kill_switch():
    bus = EventBus()
    rm = RiskManager(bus=bus)
    kills = []
    async def on_alert(msg):
        if msg.payload.get("action") == "firm_kill_switch":
            kills.append(msg)
    await bus.subscribe("risk.alert", on_alert)
    await rm.firm_kill_switch("ceo", "market crash")
    await asyncio.sleep(0.05)
    assert len(kills) == 1
    assert kills[0].payload["authorized_by"] == "ceo"
