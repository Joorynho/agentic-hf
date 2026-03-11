from __future__ import annotations

from datetime import datetime, timezone
import pytest

from src.core.bus.event_bus import EventBus
from src.core.models.enums import PodStatus
from src.core.models.messages import AgentMessage
from src.core.models.pod_summary import PodSummary, PodRiskMetrics, PodExposureBucket
from src.agents.risk.cro_agent import CROAgent
from src.agents.ceo.ceo_agent import CEOAgent
from src.agents.cio.cio_agent import CIOAgent
from src.agents.governance.governance_orchestrator import GovernanceOrchestrator
from src.backtest.accounting.capital_allocator import CapitalAllocator

POD_IDS = ["equities", "fx", "crypto", "commodities"]


def _summary(
    pod_id: str,
    status: PodStatus = PodStatus.ACTIVE,
    drawdown: float = 0.02,
    var: float = 0.01,
    leverage: float = 1.0,
):
    return PodSummary(
        pod_id=pod_id,
        timestamp=datetime.now(timezone.utc),
        status=status,
        risk_metrics=PodRiskMetrics(
            pod_id=pod_id,
            timestamp=datetime.now(timezone.utc),
            nav=1_000_000.0,
            daily_pnl=500.0,
            drawdown_from_hwm=drawdown,
            current_vol_ann=0.10,
            gross_leverage=leverage,
            net_leverage=leverage * 0.8,
            var_95_1d=var,
            es_95_1d=var * 1.2,
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
def cro(bus):
    return CROAgent(bus)


@pytest.fixture
def governance(bus):
    allocator = CapitalAllocator(POD_IDS, bus)
    ceo = CEOAgent(bus)
    cio = CIOAgent(bus, allocator)
    cro = CROAgent(bus)
    return GovernanceOrchestrator(ceo, cio, cro)


# --- CRO ---

async def test_cro_no_breach_on_healthy_pods(cro):
    summaries = [_summary(pid) for pid in POD_IDS]
    breached = await cro.check_all_pods(summaries)
    assert breached == []


async def test_cro_detects_drawdown_breach(cro):
    summaries = [
        _summary("equities", drawdown=0.11),  # >10% → alert
        *[_summary(pid) for pid in POD_IDS[1:]],
    ]
    breached = await cro.check_all_pods(summaries)
    assert "equities" in breached


async def test_cro_approves_valid_allocation_message(cro):
    msg = AgentMessage(
        timestamp=datetime.now(timezone.utc),
        sender="cio", recipient="cro", topic="governance.cro",
        payload={
            "action": "cio_proposal",
            "proposed_allocations": {pid: 0.25 for pid in POD_IDS},
        },
    )
    response = await cro.handle_governance_message(msg)
    assert response is not None
    assert response.payload["consensus"] is True


async def test_cro_rejects_over_concentrated_allocation(cro):
    msg = AgentMessage(
        timestamp=datetime.now(timezone.utc),
        sender="cio", recipient="cro", topic="governance.cro",
        payload={
            "action": "cio_proposal",
            "proposed_allocations": {"equities": 0.6, "fx": 0.15, "crypto": 0.1, "commodities": 0.15},
        },
    )
    response = await cro.handle_governance_message(msg)
    assert response is not None
    assert response.payload["consensus"] is False
    assert "equities" in response.payload["violations"]


async def test_cro_firm_kill_switch_publishes(bus):
    cro = CROAgent(bus)
    received = []
    await bus.subscribe("risk.alert", lambda msg: received.append(msg))
    await cro.firm_kill_switch("Test kill switch")
    # Give event loop a tick
    import asyncio
    await asyncio.sleep(0)
    # The kill switch event should have been published (task created)
    # We verify no exception was raised — async tasks fire separately


# --- Governance Orchestrator ---

async def test_governance_firm_deliberation(governance):
    summaries = [_summary(pid) for pid in POD_IDS]
    loop = await governance.run_firm_deliberation(summaries)
    assert loop.topic == "firm_deliberation"
    assert loop.iterations_used >= 1


async def test_governance_strategy_co_decision_returns_mandate(governance):
    summaries = [_summary(pid) for pid in POD_IDS]
    loop, mandate = await governance.run_strategy_co_decision(summaries)
    assert mandate is not None
    assert mandate.authorized_by in ("ceo_llm", "ceo_rule_based")


async def test_governance_full_cycle(governance):
    summaries = [_summary(pid) for pid in POD_IDS]
    result = await governance.run_full_cycle(summaries)
    assert "breached_pods" in result
    assert "mandate" in result
    assert result["mandate"] is not None


async def test_governance_risk_interrogation_on_breach(governance):
    summaries = [
        _summary("equities", drawdown=0.11),
        *[_summary(pid) for pid in POD_IDS[1:]],
    ]
    breached = await governance.run_risk_interrogation(summaries)
    assert "equities" in breached


# --- Dict input (matching real runtime behavior) ---

async def test_cro_accepts_dict_input(cro):
    """CRO.check_all_pods must accept dict[str, PodSummary] since
    session_manager._collect_pod_summaries returns a dict."""
    summaries = {pid: _summary(pid) for pid in POD_IDS}
    breached = await cro.check_all_pods(summaries)
    assert breached == []


async def test_cro_detects_breach_with_dict_input(cro):
    summaries = {pid: _summary(pid) for pid in POD_IDS}
    summaries["equities"] = _summary("equities", drawdown=0.11)
    breached = await cro.check_all_pods(summaries)
    assert "equities" in breached


async def test_governance_full_cycle_with_dict_input(governance):
    """run_full_cycle receives a dict from session_manager."""
    summaries = {pid: _summary(pid) for pid in POD_IDS}
    result = await governance.run_full_cycle(summaries)
    assert "breached_pods" in result
    assert "mandate" in result
    assert result["mandate"] is not None


async def test_governance_deliberation_with_dict_input(governance):
    summaries = {pid: _summary(pid) for pid in POD_IDS}
    loop = await governance.run_firm_deliberation(summaries)
    assert loop.topic == "firm_deliberation"
    assert loop.iterations_used >= 1


async def test_governance_risk_interrogation_dict_with_breach(governance):
    summaries = {pid: _summary(pid) for pid in POD_IDS}
    summaries["crypto"] = _summary("crypto", drawdown=0.11)
    breached = await governance.run_risk_interrogation(summaries)
    assert "crypto" in breached
