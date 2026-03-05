import pytest, asyncio
from src.pods.base.namespace import PodNamespace
from src.core.bus.event_bus import EventBus
from src.core.bus.exceptions import TopicAccessError
from src.core.models.messages import AgentMessage
from src.core.models.pod_summary import PodSummary, PodRiskMetrics, PodExposureBucket
from src.core.models.enums import PodStatus
from datetime import datetime

def test_pod_cannot_read_sibling_namespace():
    ns_alpha = PodNamespace("alpha")
    ns_beta = PodNamespace("beta")
    ns_alpha.set("signal", 0.95)
    assert ns_beta.get("signal") is None

def test_pod_namespace_key_scoped_internally():
    ns_alpha = PodNamespace("alpha")
    ns_alpha.set("signal", 0.95)
    ns_beta = PodNamespace("beta")
    assert ns_beta.get("alpha::signal") is None

@pytest.mark.asyncio
async def test_pod_cannot_publish_to_sibling_gateway():
    bus = EventBus()
    msg = AgentMessage(timestamp=datetime.now(), sender="pod.alpha",
                       recipient="pod.beta", topic="pod.beta.gateway", payload={})
    with pytest.raises(TopicAccessError):
        await bus.publish("pod.beta.gateway", msg, publisher_id="pod.alpha")

@pytest.mark.asyncio
async def test_governance_not_receivable_by_wrong_pod():
    bus = EventBus()
    received_alpha = []
    await bus.subscribe("governance.alpha", lambda m: received_alpha.append(m))
    msg = AgentMessage(timestamp=datetime.now(), sender="cio",
                       recipient="pod.beta", topic="governance.beta",
                       payload={"action": "rebalance"})
    await bus.publish("governance.beta", msg, publisher_id="cio")
    await asyncio.sleep(0.05)
    assert len(received_alpha) == 0

def test_pod_summary_has_no_raw_positions_or_signals():
    metrics = PodRiskMetrics(
        pod_id="alpha", timestamp=datetime.now(), nav=1e6,
        daily_pnl=5000, drawdown_from_hwm=-0.01, current_vol_ann=0.09,
        gross_leverage=1.2, net_leverage=0.8, var_95_1d=0.012, es_95_1d=0.018)
    summary = PodSummary(
        pod_id="alpha", timestamp=datetime.now(), status=PodStatus.ACTIVE,
        risk_metrics=metrics,
        exposure_buckets=[PodExposureBucket(asset_class="equity_us", direction="long", notional_pct_nav=0.85)],
        expected_return_estimate=0.12, turnover_daily_pct=0.05, heartbeat_ok=True)
    fields = set(summary.model_fields.keys())
    assert "positions" not in fields
    assert "signal_value" not in fields
    assert "model_params" not in fields
    assert "strategy_tag" not in fields
