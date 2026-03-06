"""MVP3 Batch 3 Integration Tests — Agent Reasoning Visibility.

Covers:
1. SessionLogger correctly creates and populates reasoning.jsonl
2. SessionLogger correctly creates and populates conversations.jsonl
3. CEOAgent, CIOAgent, and GovernanceOrchestrator all accept SessionLogger
4. Reasoning capture works end-to-end
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.agents.ceo.ceo_agent import CEOAgent
from src.agents.cio.cio_agent import CIOAgent
from src.agents.governance.governance_orchestrator import GovernanceOrchestrator
from src.agents.risk.cro_agent import CROAgent
from src.backtest.accounting.capital_allocator import CapitalAllocator
from src.core.bus.audit_log import AuditLog
from src.core.bus.collaboration_runner import CollaborationRunner
from src.core.bus.event_bus import EventBus
from src.core.models.collaboration import CollaborationLoop
from src.core.models.enums import PodStatus
from src.core.models.messages import AgentMessage
from src.core.models.pod_summary import PodExposureBucket, PodRiskMetrics, PodSummary
from src.mission_control.session_logger import SessionLogger

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


def _make_all_summaries() -> list[PodSummary]:
    return [_make_summary(pid) for pid in POD_IDS]


def test_session_logger_captures_reasoning_files():
    """Test that SessionLogger creates and populates reasoning.jsonl with proper format."""
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = SessionLogger(session_dir=tmpdir)

        # Log reasoning entries for two agents
        logger.log_reasoning("ceo", "prompt", "Sample CEO prompt text")
        logger.log_reasoning("ceo", "response", '{"outcome": "approved"}')
        logger.log_reasoning("ceo", "decision", "Mandate approved with constraints")

        logger.log_reasoning("cio", "prompt", "Sample CIO prompt text")
        logger.log_reasoning("cio", "response", '{"allocation": 0.5}')
        logger.log_reasoning("cio", "decision", "Rebalance applied")

        logger.close()

        # Verify reasoning.jsonl exists
        reasoning_file = Path(tmpdir) / "reasoning.jsonl"
        assert reasoning_file.exists(), "reasoning.jsonl should exist"

        # Read and verify JSONL format and content
        lines = reasoning_file.read_text().strip().split("\n")
        assert len(lines) >= 6, f"Expected at least 6 lines, got {len(lines)}"

        # Verify each line is valid JSON with required fields
        entries = []
        for line in lines:
            entry = json.loads(line)
            entries.append(entry)

            # Check required fields
            assert "timestamp" in entry, "Missing timestamp"
            assert "agent" in entry, "Missing agent"
            assert "event" in entry, "Missing event"
            assert "content" in entry, "Missing content"

            # Verify agent and event types
            assert entry["agent"] in ("ceo", "cio"), f"Unexpected agent: {entry['agent']}"
            assert entry["event"] in ("prompt", "response", "decision"), f"Unexpected event: {entry['event']}"

        # Verify timestamps are ISO format
        for entry in entries:
            try:
                datetime.fromisoformat(entry["timestamp"])
            except ValueError:
                pytest.fail(f"Invalid ISO timestamp: {entry['timestamp']}")


def test_session_logger_creates_conversations_file():
    """Test that SessionLogger creates conversations.jsonl after logging collaboration loop."""
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = SessionLogger(session_dir=tmpdir)

        # Create a mock collaboration loop
        msg1 = AgentMessage(
            timestamp=datetime.now(timezone.utc),
            sender="cio",
            recipient="cro",
            topic="governance.deliberation",
            payload={"action": "proposal", "summary": "Capital rebalance"},
        )
        msg2 = AgentMessage(
            timestamp=datetime.now(timezone.utc),
            sender="cro",
            recipient="cio",
            topic="governance.deliberation",
            payload={"consensus": True, "outcome": {"approved": True}},
        )

        loop = CollaborationLoop(
            topic="test_loop",
            participants=["cio", "cro"],
            max_iterations=5,
            messages=[msg1, msg2],
            consensus_reached=True,
            outcome={"approved": True},
            iterations_used=2,
            started_at=datetime.now(timezone.utc),
        )

        # Log the collaboration loop
        logger.log_collaboration_loop(loop)
        logger.close()

        # Verify conversations.jsonl exists
        conversations_file = Path(tmpdir) / "conversations.jsonl"
        assert conversations_file.exists(), "conversations.jsonl should exist"

        # Read and verify content
        lines = conversations_file.read_text().strip().split("\n")
        assert len(lines) >= 1, "conversations.jsonl should have at least one entry"

        entry = json.loads(lines[0])
        assert entry["topic"] == "test_loop"
        assert entry["consensus_reached"] is True
        assert "messages" in entry
        assert len(entry["messages"]) >= 2


def test_ceo_agent_has_session_logger_parameter():
    """Test that CEOAgent accepts and stores session_logger parameter."""
    with tempfile.TemporaryDirectory() as tmpdir:
        bus = EventBus(audit_log=AuditLog())
        logger = SessionLogger(session_dir=tmpdir)

        # Create CEOAgent with session_logger
        ceo = CEOAgent(bus=bus, session_logger=logger)

        # Verify the agent stored the logger
        assert ceo._session_logger is logger, "CEOAgent should store session_logger"

        logger.close()


def test_cio_agent_has_session_logger_parameter():
    """Test that CIOAgent accepts and stores session_logger parameter."""
    with tempfile.TemporaryDirectory() as tmpdir:
        bus = EventBus(audit_log=AuditLog())
        allocator = CapitalAllocator(pod_ids=POD_IDS, bus=bus)
        logger = SessionLogger(session_dir=tmpdir)

        # Create CIOAgent with session_logger
        cio = CIOAgent(bus=bus, allocator=allocator, session_logger=logger)

        # Verify the agent stored the logger
        assert cio._session_logger is logger, "CIOAgent should store session_logger"

        logger.close()


def test_governance_orchestrator_has_session_logger_parameter():
    """Test that GovernanceOrchestrator accepts and stores session_logger parameter."""
    with tempfile.TemporaryDirectory() as tmpdir:
        bus = EventBus(audit_log=AuditLog())
        allocator = CapitalAllocator(pod_ids=POD_IDS, bus=bus)
        logger = SessionLogger(session_dir=tmpdir)

        # Create agents with session_logger
        ceo = CEOAgent(bus=bus, session_logger=logger)
        cio = CIOAgent(bus=bus, allocator=allocator, session_logger=logger)
        cro = CROAgent(bus=bus)

        # Create GovernanceOrchestrator with session_logger
        orch = GovernanceOrchestrator(ceo=ceo, cio=cio, cro=cro, session_logger=logger)

        # Verify the orchestrator stored the logger
        assert orch._session_logger is logger, "GovernanceOrchestrator should store session_logger"

        logger.close()


@pytest.mark.asyncio
async def test_reasoning_capture_end_to_end():
    """Test end-to-end reasoning capture: agents log decisions and conversations persist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        bus = EventBus(audit_log=AuditLog())
        allocator = CapitalAllocator(pod_ids=POD_IDS, bus=bus)
        logger = SessionLogger(session_dir=tmpdir)

        # Create agents with session_logger
        ceo = CEOAgent(bus=bus, session_logger=logger)
        cio = CIOAgent(bus=bus, allocator=allocator, session_logger=logger)
        cro = CROAgent(bus=bus)

        # Create governance orchestrator with session_logger
        runner = CollaborationRunner(session_logger=logger)
        orch = GovernanceOrchestrator(ceo=ceo, cio=cio, cro=cro, runner=runner, session_logger=logger)

        # Simulate a CEO mandate approval (will log reasoning)
        summaries = _make_all_summaries()

        # Call CEO mandate approval to trigger reasoning logging
        mandate = await ceo.approve_mandate(summaries)

        # Verify mandate was created
        assert mandate is not None
        assert mandate.narrative is not None

        logger.close()

        # Verify reasoning.jsonl was populated
        reasoning_file = Path(tmpdir) / "reasoning.jsonl"
        assert reasoning_file.exists()

        # Should have decision entry from mandate approval
        lines = reasoning_file.read_text().strip().split("\n")
        assert len(lines) >= 1, "reasoning.jsonl should have at least one entry"

        # Check that there's a decision entry from CEO
        decision_found = False
        for line in lines:
            entry = json.loads(line)
            if entry.get("agent") == "ceo" and entry.get("event") == "decision":
                decision_found = True
                assert "Mandate approved" in entry.get("content", "")

        assert decision_found, "Should have CEO decision entry in reasoning.jsonl"
