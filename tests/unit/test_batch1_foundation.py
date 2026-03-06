"""Batch 1 unit tests — new models, Polymarket adapter, capital allocator, collaboration runner."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from src.core.models.allocation import AllocationRecord, MandateUpdate
from src.core.models.collaboration import CollaborationLoop
from src.core.models.enums import EventType
from src.core.models.messages import AgentMessage
from src.core.models.polymarket import PolymarketSignal


# ---------------------------------------------------------------------------
# PolymarketSignal
# ---------------------------------------------------------------------------


def test_polymarket_signal_valid():
    sig = PolymarketSignal(
        market_id="abc123",
        question="Will the Fed cut rates in March?",
        yes_price=0.65,
        no_price=0.35,
        implied_prob=0.65,
        spread=0.02,
        volume_24h=10000.0,
        open_interest=50000.0,
        timestamp=datetime.now(timezone.utc),
        tags=["fed", "macro"],
    )
    assert sig.implied_prob == pytest.approx(0.65, abs=1e-5)
    assert sig.market_id == "abc123"


def test_polymarket_signal_rejects_invalid_probability():
    with pytest.raises(Exception):
        PolymarketSignal(
            market_id="x",
            question="q",
            yes_price=1.5,  # invalid
            no_price=0.3,
            implied_prob=0.6,
            spread=0.01,
            volume_24h=0,
            open_interest=0,
            timestamp=datetime.now(timezone.utc),
        )


def test_polymarket_signal_frozen():
    sig = PolymarketSignal(
        market_id="x",
        question="q",
        yes_price=0.6,
        no_price=0.4,
        implied_prob=0.6,
        spread=0.01,
        volume_24h=0,
        open_interest=0,
        timestamp=datetime.now(timezone.utc),
    )
    with pytest.raises(Exception):
        sig.yes_price = 0.9  # type: ignore[misc]


# ---------------------------------------------------------------------------
# AllocationRecord + MandateUpdate
# ---------------------------------------------------------------------------


def test_allocation_record_fields():
    now = datetime.now(timezone.utc)
    rec = AllocationRecord(
        timestamp=now,
        pod_id="alpha",
        old_pct=0.2,
        new_pct=0.25,
        rationale="Alpha outperforming",
        authorized_by="cio_llm",
    )
    assert rec.pod_id == "alpha"
    assert rec.new_pct == 0.25


def test_mandate_update_defaults():
    m = MandateUpdate(
        timestamp=datetime.now(timezone.utc),
        narrative="Risk-off regime",
        objectives=["Preserve capital"],
        constraints={"max_leverage": 1.0},
        rationale="VIX spike",
        authorized_by="ceo_rule_based",
    )
    assert m.cio_approved is False
    assert m.cro_approved is False


# ---------------------------------------------------------------------------
# CollaborationLoop
# ---------------------------------------------------------------------------


def test_collaboration_loop_initial_state():
    loop = CollaborationLoop(
        topic="pm_risk_signoff",
        participants=["pm.alpha", "risk.alpha"],
        max_iterations=10,
        started_at=datetime.now(timezone.utc),
    )
    assert loop.consensus_reached is False
    assert loop.iterations_used == 0
    assert loop.messages == []


# ---------------------------------------------------------------------------
# New EventType values
# ---------------------------------------------------------------------------


def test_new_event_types_exist():
    assert EventType.POLYMARKET_SIGNAL == "polymarket_signal"
    assert EventType.COLLABORATION_START == "collaboration_start"
    assert EventType.COLLABORATION_END == "collaboration_end"
    assert EventType.GOVERNANCE_QUERY == "governance_query"
    assert EventType.GOVERNANCE_RESPONSE == "governance_response"
    assert EventType.RISK_ALERT == "risk_alert"


# ---------------------------------------------------------------------------
# CapitalAllocator
# ---------------------------------------------------------------------------


@pytest.fixture
def bus_and_allocator():
    from src.core.bus.event_bus import EventBus
    from src.backtest.accounting.capital_allocator import CapitalAllocator

    bus = EventBus()
    alloc = CapitalAllocator(["alpha", "beta", "gamma", "delta", "epsilon"], bus)
    return bus, alloc


def test_capital_allocator_initial_equal_weight(bus_and_allocator):
    _, alloc = bus_and_allocator
    allocs = alloc.current_allocations()
    assert len(allocs) == 5
    assert abs(sum(allocs.values()) - 1.0) < 0.001
    for v in allocs.values():
        assert abs(v - 0.2) < 0.001


def test_capital_allocator_validate_rejects_bad_sum(bus_and_allocator):
    _, alloc = bus_and_allocator
    now = datetime.now(timezone.utc)
    records = [
        AllocationRecord(timestamp=now, pod_id="alpha", old_pct=0.2, new_pct=0.5,
                         rationale="x", authorized_by="cio_rule_based"),
        AllocationRecord(timestamp=now, pod_id="beta", old_pct=0.2, new_pct=0.5,
                         rationale="x", authorized_by="cio_rule_based"),
        # gamma/delta/epsilon remain at 0.2 each → sum = 0.5+0.5+0.2+0.2+0.2 = 1.6
    ]
    ok, reason = alloc.validate(records)
    assert not ok
    assert "1.0" in reason


async def test_capital_allocator_apply_valid(bus_and_allocator):
    _, alloc = bus_and_allocator
    now = datetime.now(timezone.utc)
    records = [
        AllocationRecord(timestamp=now, pod_id="alpha", old_pct=0.2, new_pct=0.3,
                         rationale="r", authorized_by="cio_llm"),
        AllocationRecord(timestamp=now, pod_id="beta", old_pct=0.2, new_pct=0.1,
                         rationale="r", authorized_by="cio_llm"),
    ]
    await alloc.apply_allocation(records)
    assert alloc.get("alpha") == pytest.approx(0.3)
    assert alloc.get("beta") == pytest.approx(0.1)


# ---------------------------------------------------------------------------
# CollaborationRunner
# ---------------------------------------------------------------------------


class _EchoAgent:
    """Stub agent that immediately signals consensus."""

    def __init__(self, agent_id: str, respond_consensus: bool = True):
        self.agent_id = agent_id
        self._respond_consensus = respond_consensus

    async def handle_governance_message(self, msg: AgentMessage) -> AgentMessage | None:
        return AgentMessage(
            timestamp=datetime.now(timezone.utc),
            sender=self.agent_id,
            recipient=msg.sender,
            topic=msg.topic,
            payload={"consensus": self._respond_consensus, "outcome": {"action": "approve"}},
            correlation_id=msg.id,
        )


async def test_collaboration_runner_reaches_consensus():
    from src.core.bus.collaboration_runner import CollaborationRunner

    runner = CollaborationRunner()
    agents = [_EchoAgent("pm.alpha"), _EchoAgent("risk.alpha")]
    initial = AgentMessage(
        timestamp=datetime.now(timezone.utc),
        sender="pm.alpha",
        recipient="risk.alpha",
        topic="pm_risk",
        payload={"order": "buy 100 AAPL"},
    )
    loop = await runner.run_loop("pm_risk_signoff", agents, max_iterations=5, initial_message=initial)
    assert loop.consensus_reached is True
    assert loop.iterations_used == 1


async def test_collaboration_runner_no_consensus_holds():
    from src.core.bus.collaboration_runner import CollaborationRunner

    runner = CollaborationRunner()
    agents = [_EchoAgent("pm", respond_consensus=False), _EchoAgent("risk", respond_consensus=False)]
    initial = AgentMessage(
        timestamp=datetime.now(timezone.utc),
        sender="pm",
        recipient="risk",
        topic="pm_risk",
        payload={"order": "buy"},
    )
    loop = await runner.run_loop("pm_risk", agents, max_iterations=3, initial_message=initial)
    assert loop.consensus_reached is False
    assert loop.outcome["action"] == "hold"
    assert loop.iterations_used == 3
