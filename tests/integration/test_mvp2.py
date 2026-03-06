"""MVP2 integration tests.

Covers:
1. Full governance loop (CEO + CIO + CRO + 5 pod summaries)
2. CapitalAllocator sum=1.0 invariant across reallocation
3. Polymarket adapter graceful fallback (no API key)
4. CollaborationRunner bounded iteration
5. CRO auto-halt on drawdown breach
6. Mandate fields and allocation weights correct
7. Governance cycle identifies breached pod
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from src.agents.ceo.ceo_agent import CEOAgent
from src.agents.cio.cio_agent import CIOAgent
from src.agents.governance.governance_orchestrator import GovernanceOrchestrator
from src.agents.risk.cro_agent import CROAgent
from src.backtest.accounting.capital_allocator import CapitalAllocator
from src.core.bus.audit_log import AuditLog
from src.core.bus.event_bus import EventBus
from src.core.models.enums import PodStatus
from src.core.models.messages import AgentMessage
from src.core.models.pod_summary import PodExposureBucket, PodRiskMetrics, PodSummary
from src.data.adapters.polymarket_adapter import PolymarketAdapter


POD_IDS = ["alpha", "beta", "gamma", "delta", "epsilon"]


def _make_summary(
    pod_id: str,
    drawdown: float = 0.03,
    vol: float = 0.09,
    leverage: float = 1.2,
    var: float = 0.004,
    status: PodStatus = PodStatus.ACTIVE,
) -> PodSummary:
    return PodSummary(
        pod_id=pod_id,
        timestamp=datetime.now(timezone.utc),
        status=status,
        risk_metrics=PodRiskMetrics(
            pod_id=pod_id,
            timestamp=datetime.now(timezone.utc),
            nav=2_000_000,
            daily_pnl=5_000,
            drawdown_from_hwm=drawdown,
            current_vol_ann=vol,
            gross_leverage=leverage,
            net_leverage=leverage * 0.8,
            var_95_1d=var,
            es_95_1d=var * 1.3,
        ),
        exposure_buckets=[
            PodExposureBucket(asset_class="equity", direction="long", notional_pct_nav=0.80),
            PodExposureBucket(asset_class="cash", direction="long", notional_pct_nav=0.20),
        ],
        expected_return_estimate=0.08,
        turnover_daily_pct=0.02,
        heartbeat_ok=True,
    )


def _make_all_summaries(overrides=None):
    overrides = overrides or {}
    return [_make_summary(pid, **overrides.get(pid, {})) for pid in POD_IDS]


def _make_governance(bus=None):
    bus = bus or EventBus(audit_log=AuditLog())
    allocator = CapitalAllocator(pod_ids=POD_IDS, bus=bus)
    ceo = CEOAgent(bus=bus)
    cio = CIOAgent(bus=bus, allocator=allocator)
    cro = CROAgent(bus=bus)
    return GovernanceOrchestrator(ceo=ceo, cio=cio, cro=cro)


# 1. Full governance cycle

@pytest.mark.asyncio
async def test_full_governance_cycle_returns_mandate():
    orch = _make_governance()
    result = await orch.run_full_cycle(_make_all_summaries())
    assert "mandate" in result and "breached_pods" in result
    assert result["mandate"].authorized_by in ("ceo_llm", "ceo_rule_based")
    assert isinstance(result["mandate"].objectives, list)


@pytest.mark.asyncio
async def test_full_governance_cycle_no_breaches_on_healthy_pods():
    orch = _make_governance()
    result = await orch.run_full_cycle(_make_all_summaries())
    assert result["breached_pods"] == []


# 2. CRO breach detection

@pytest.mark.asyncio
async def test_cro_halts_on_drawdown_breach():
    bus = EventBus(audit_log=AuditLog())
    cro = CROAgent(bus=bus)
    alerted = []
    await bus.subscribe("risk.alert", lambda msg: alerted.append(msg))
    breached = await cro.check_all_pods(
        _make_all_summaries(overrides={"delta": {"drawdown": 0.11}})
    )
    await asyncio.sleep(0.05)
    assert "delta" in breached
    assert len(alerted) > 0


@pytest.mark.asyncio
async def test_cro_no_halt_below_10pct():
    bus = EventBus(audit_log=AuditLog())
    cro = CROAgent(bus=bus)
    breached = await cro.check_all_pods(
        _make_all_summaries(overrides={"alpha": {"drawdown": 0.085}})
    )
    assert "alpha" not in breached


# 3. CapitalAllocator invariant

@pytest.mark.asyncio
async def test_capital_allocator_sum_invariant():
    bus = EventBus()
    allocator = CapitalAllocator(pod_ids=POD_IDS, bus=bus)
    allocs = allocator.current_allocations()
    assert abs(sum(allocs.values()) - 1.0) < 1e-9


@pytest.mark.asyncio
async def test_cio_rebalance_sum_invariant():
    bus = EventBus(audit_log=AuditLog())
    allocator = CapitalAllocator(pod_ids=POD_IDS, bus=bus)
    cio = CIOAgent(bus=bus, allocator=allocator)
    with patch.dict(os.environ, {"OPENAI_API_KEY": "", "ANTHROPIC_API_KEY": ""}):
        records = await cio.rebalance(_make_all_summaries())
    assert len(records) == 5
    assert abs(sum(r.new_pct for r in records) - 1.0) < 1e-6
    for r in records:
        assert 0.0 <= r.new_pct <= 1.0


# 4. Polymarket fallback

def test_polymarket_adapter_no_key():
    adapter = PolymarketAdapter(api_key="")
    assert not adapter._has_key


@pytest.mark.asyncio
async def test_polymarket_adapter_returns_empty_without_key():
    signals = await PolymarketAdapter(api_key="").fetch_signals(tags=["fed-rate-cut"])
    assert signals == []


# 5. Collaboration runner bounded (via orchestrator)

@pytest.mark.asyncio
async def test_governance_loop_bounded():
    orch = _make_governance()
    loop = await orch.run_firm_deliberation(_make_all_summaries())
    assert loop.iterations_used <= 5
    assert loop.completed_at is not None


@pytest.mark.asyncio
async def test_governance_strategy_co_decision_completes():
    orch = _make_governance()
    loop, mandate = await orch.run_strategy_co_decision(_make_all_summaries())
    assert loop.iterations_used >= 1
    assert mandate is not None


# 6. CEO mandate rule-based path

@pytest.mark.asyncio
async def test_ceo_rule_based_mandate():
    with patch.dict(os.environ, {"OPENAI_API_KEY": "", "ANTHROPIC_API_KEY": ""}):
        bus = EventBus()
        ceo = CEOAgent(bus=bus)
        mandate = await ceo.approve_mandate(_make_all_summaries())
    assert mandate.authorized_by == "ceo_rule_based"
    assert len(mandate.objectives) >= 1


# 7. Breached pod surfaced

@pytest.mark.asyncio
async def test_governance_cycle_identifies_breach():
    orch = _make_governance()
    summaries = _make_all_summaries(overrides={"epsilon": {"drawdown": 0.13}})
    result = await orch.run_full_cycle(summaries)
    assert "epsilon" in result["breached_pods"]
    assert result["mandate"] is not None
