from __future__ import annotations

from datetime import datetime, timezone
import pytest

from src.core.bus.event_bus import EventBus
from src.core.models.messages import AgentMessage
from src.core.models.pod_summary import PodSummary, PodRiskMetrics, PodExposureBucket
from src.agents.ceo.ceo_agent import CEOAgent
from src.agents.cio.cio_agent import CIOAgent
from src.backtest.accounting.capital_allocator import CapitalAllocator


POD_IDS = ["alpha", "beta", "gamma", "delta", "epsilon"]


def _summary(pod_id: str, status: str = "active", pnl: float = 0.0, dd: float = 0.0):
    return PodSummary(
        pod_id=pod_id,
        timestamp=datetime.now(timezone.utc),
        status=status,
        risk_metrics=PodRiskMetrics(
            pod_id=pod_id,
            timestamp=datetime.now(timezone.utc),
            nav=1_000_000.0,
            daily_pnl=pnl,
            drawdown_from_hwm=dd,
            current_vol_ann=0.10,
            gross_leverage=1.0,
            net_leverage=1.0,
            var_95_1d=0.01,
            es_95_1d=0.012,
        ),
        exposure_buckets=[
            PodExposureBucket(asset_class="equity", direction="long", notional_pct_nav=0.8)
        ],
        expected_return_estimate=0.08,
        turnover_daily_pct=0.02,
        heartbeat_ok=True,
    )


@pytest.fixture
def bus():
    return EventBus()


@pytest.fixture
def allocator(bus):
    return CapitalAllocator(POD_IDS, bus)


# --- CEO ---

async def test_ceo_rule_based_mandate(bus):
    ceo = CEOAgent(bus)
    summaries = [_summary(pid) for pid in POD_IDS]
    mandate = await ceo.approve_mandate(summaries)
    assert mandate.authorized_by == "ceo_rule_based"
    assert len(mandate.objectives) > 0
    assert mandate.narrative != ""


async def test_ceo_governance_message_cio_proposal(bus):
    ceo = CEOAgent(bus)
    msg = AgentMessage(
        timestamp=datetime.now(timezone.utc),
        sender="cio", recipient="ceo", topic="governance.ceo",
        payload={"action": "cio_proposal", "summary": "Increase Epsilon to 30%"},
    )
    response = await ceo.handle_governance_message(msg)
    assert response is not None
    assert response.payload["consensus"] is True


async def test_ceo_unknown_message_returns_none(bus):
    ceo = CEOAgent(bus)
    msg = AgentMessage(
        timestamp=datetime.now(timezone.utc),
        sender="cio", recipient="ceo", topic="governance.ceo",
        payload={"action": "unknown_action"},
    )
    response = await ceo.handle_governance_message(msg)
    assert response is None


# --- CIO ---

async def test_cio_rule_based_no_drift(bus, allocator):
    cio = CIOAgent(bus, allocator)
    summaries = [_summary(pid) for pid in POD_IDS]
    records = await cio.rebalance(summaries)
    assert len(records) == 5
    assert all(abs(r.new_pct - 0.2) < 0.01 for r in records)


async def test_cio_rule_based_corrects_drift(bus, allocator):
    from src.core.models.allocation import AllocationRecord
    # Force a drift: manually skew alpha to 40%
    now = datetime.now(timezone.utc)
    skew = [
        AllocationRecord(timestamp=now, pod_id="alpha", old_pct=0.2, new_pct=0.4,
                         rationale="test", authorized_by="cio_rule_based"),
        AllocationRecord(timestamp=now, pod_id="beta", old_pct=0.2, new_pct=0.15,
                         rationale="test", authorized_by="cio_rule_based"),
        AllocationRecord(timestamp=now, pod_id="gamma", old_pct=0.2, new_pct=0.15,
                         rationale="test", authorized_by="cio_rule_based"),
        AllocationRecord(timestamp=now, pod_id="delta", old_pct=0.2, new_pct=0.15,
                         rationale="test", authorized_by="cio_rule_based"),
        AllocationRecord(timestamp=now, pod_id="epsilon", old_pct=0.2, new_pct=0.15,
                         rationale="test", authorized_by="cio_rule_based"),
    ]
    await allocator.apply_allocation(skew)

    cio = CIOAgent(bus, allocator)
    summaries = [_summary(pid) for pid in POD_IDS]
    records = await cio.rebalance(summaries)
    # After correction, should be back to equal weight
    assert all(abs(r.new_pct - 0.2) < 0.01 for r in records)


async def test_cio_governance_pod_pm_counter(bus, allocator):
    cio = CIOAgent(bus, allocator)
    msg = AgentMessage(
        timestamp=datetime.now(timezone.utc),
        sender="pm.alpha", recipient="cio", topic="governance.cio",
        payload={"action": "pod_pm_counter", "pod_id": "alpha", "requested_pct": 0.30},
    )
    response = await cio.handle_governance_message(msg)
    assert response is not None
    assert response.payload["consensus"] is True
    agreed = response.payload["outcome"]["agreed_pct"]
    assert 0.2 <= agreed <= 0.30  # compromise between current 0.2 and requested 0.3


async def test_cio_validates_and_falls_back_on_bad_llm_output(bus, allocator):
    """Even if LLM returns garbage, validate() catches it and falls back to equal weight."""
    cio = CIOAgent(bus, allocator)

    async def bad_llm(*args, **kwargs):
        from src.core.models.allocation import AllocationRecord
        now = datetime.now(timezone.utc)
        # Sum = 2.0 — invalid
        return [AllocationRecord(timestamp=now, pod_id=pid, old_pct=0.2, new_pct=0.4,
                                 rationale="bad", authorized_by="cio_llm")
                for pid in POD_IDS]

    cio._llm_allocation = bad_llm
    cio._has_llm = True
    summaries = [_summary(pid) for pid in POD_IDS]
    records = await cio.rebalance(summaries)
    # Should fall back to equal weight
    assert all(abs(r.new_pct - 0.2) < 0.01 for r in records)
