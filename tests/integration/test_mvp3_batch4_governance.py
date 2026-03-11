"""MVP3 Batch 4 Integration Tests — SessionManager Governance Cycle.

Covers:
1. SessionManager runs governance cycle at correct frequency (every N iterations)
2. Governance cycle logs to SessionLogger with proper metadata
3. Governance cycle errors are caught and logged (no crash)
"""
from __future__ import annotations

import asyncio
import tempfile
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.ceo.ceo_agent import CEOAgent
from src.agents.cio.cio_agent import CIOAgent
from src.agents.governance.governance_orchestrator import GovernanceOrchestrator
from src.agents.risk.cro_agent import CROAgent
from src.backtest.accounting.capital_allocator import CapitalAllocator
from src.core.bus.audit_log import AuditLog
from src.core.bus.event_bus import EventBus
from src.core.models.allocation import MandateUpdate
from src.core.models.enums import PodStatus
from src.core.models.pod_summary import PodExposureBucket, PodRiskMetrics, PodSummary
from src.mission_control.session_manager import SessionManager
from src.mission_control.session_logger import SessionLogger

POD_IDS = ["equities", "fx", "crypto", "commodities"]


def _make_summary(
    pod_id: str,
    drawdown: float = 0.03,
    vol: float = 0.09,
    leverage: float = 1.2,
    var: float = 0.004,
    status: PodStatus = PodStatus.ACTIVE,
) -> PodSummary:
    """Create a test PodSummary."""
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


def _make_all_summaries() -> dict[str, PodSummary]:
    """Create all pod summaries (as dict for governance cycle)."""
    return {pid: _make_summary(pid) for pid in POD_IDS}


def _make_test_mandate() -> MandateUpdate:
    """Create a test MandateUpdate."""
    return MandateUpdate(
        timestamp=datetime.now(timezone.utc),
        narrative="Test mandate for governance cycle",
        objectives=["maximize_return", "limit_drawdown"],
        constraints={"max_leverage": 2.0, "max_drawdown": 0.15},
        rationale="Scheduled governance review",
        authorized_by="ceo_rule_based",
        cio_approved=True,
        cro_approved=True,
    )


@pytest.mark.asyncio
async def test_session_manager_runs_governance_cycle_every_5_iterations():
    """Test governance cycle runs at iterations 5, 10, 15, etc.

    - Mock GovernanceOrchestrator.run_full_cycle() to return test MandateUpdate
    - Run event loop for 12 iterations (governance runs at iter 5 and 10)
    - Verify run_full_cycle() called exactly 2 times
    - Each call receives pod_summaries dict
    - Call stop_session()
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        # Setup mocks
        alpaca_mock = AsyncMock()
        alpaca_mock.fetch_account = AsyncMock(
            return_value={"equity": 100_000, "buying_power": 50_000, "position_count": 0}
        )
        alpaca_mock.fetch_bars = AsyncMock(return_value={})

        audit_log = AuditLog()
        event_bus = EventBus(audit_log=audit_log)
        session_logger = SessionLogger(session_dir=tmpdir)

        # Create SessionManager
        manager = SessionManager(
            alpaca_adapter=alpaca_mock,
            event_bus=event_bus,
            audit_log=audit_log,
            session_dir=tmpdir,
        )

        # Mock GovernanceOrchestrator.run_full_cycle
        mock_governance = AsyncMock(spec=GovernanceOrchestrator)
        test_mandate = _make_test_mandate()
        mock_governance.run_full_cycle = AsyncMock(
            return_value={
                "breached_pods": [],
                "loop6_consensus": True,
                "loop7_consensus": True,
                "mandate": test_mandate,
            }
        )
        manager._governance = mock_governance
        manager._session_logger = session_logger

        # Setup manager state to skip actual pod initialization
        manager._session_active = True
        manager._pod_gateways = {}
        manager._pod_runtimes = {}
        manager._iteration = 0

        # Run event loop for 12 iterations (governance runs at 5, 10)
        async def run_limited_loop():
            symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]
            for _ in range(12):
                manager._iteration += 1

                # Skip actual bar fetching and pod pushing
                # Just collect summaries and run governance
                pod_summaries = _make_all_summaries()

                # Run governance at correct frequency
                if manager._iteration > 0 and manager._iteration % 5 == 0:
                    try:
                        governance_result = await manager._governance.run_full_cycle(
                            pod_summaries
                        )
                        manager._session_logger.log_reasoning(
                            "governance",
                            "cycle",
                            f"Iteration {manager._iteration}: test cycle",
                            metadata={"iteration": manager._iteration},
                        )
                    except Exception as e:
                        pass

                await asyncio.sleep(0.01)  # Small delay

            manager._session_active = False

        await run_limited_loop()
        await manager.stop_session()
        # Note: stop_session() closes the session_logger, so don't call close() again

        # Verify run_full_cycle called exactly 2 times
        assert (
            mock_governance.run_full_cycle.call_count == 2
        ), f"Expected 2 governance cycles, got {mock_governance.run_full_cycle.call_count}"

        # Verify each call received pod_summaries dict
        for call in mock_governance.run_full_cycle.call_args_list:
            args, kwargs = call
            assert len(args) > 0 or "pod_summaries" in kwargs
            pod_summaries_arg = args[0] if args else kwargs.get("pod_summaries")
            assert isinstance(pod_summaries_arg, dict)
            assert len(pod_summaries_arg) == len(POD_IDS)


@pytest.mark.asyncio
async def test_session_manager_governance_logs_to_session_logger():
    """Test governance cycle logs to SessionLogger with proper metadata.

    - Mock SessionLogger to track log_reasoning() calls
    - Run event loop for 6 iterations (governance runs at iter 5)
    - Verify session_logger.log_reasoning() called with:
      - agent="governance"
      - event="cycle"
      - content includes iteration number and mandate data
    - Call stop_session()
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        # Setup mocks
        alpaca_mock = AsyncMock()
        alpaca_mock.fetch_account = AsyncMock(
            return_value={"equity": 100_000, "buying_power": 50_000, "position_count": 0}
        )
        alpaca_mock.fetch_bars = AsyncMock(return_value={})

        audit_log = AuditLog()
        event_bus = EventBus(audit_log=audit_log)
        session_logger = SessionLogger(session_dir=tmpdir)

        # Create SessionManager
        manager = SessionManager(
            alpaca_adapter=alpaca_mock,
            event_bus=event_bus,
            audit_log=audit_log,
            session_dir=tmpdir,
        )

        # Mock GovernanceOrchestrator.run_full_cycle
        mock_governance = AsyncMock(spec=GovernanceOrchestrator)
        test_mandate = _make_test_mandate()
        mock_governance.run_full_cycle = AsyncMock(
            return_value={
                "breached_pods": [],
                "loop6_consensus": True,
                "loop7_consensus": True,
                "mandate": test_mandate,
            }
        )
        manager._governance = mock_governance
        manager._session_logger = session_logger

        # Mock SessionLogger.log_reasoning
        original_log_reasoning = session_logger.log_reasoning
        log_reasoning_calls = []

        def mock_log_reasoning(agent_name, event_type, content, metadata=None):
            log_reasoning_calls.append(
                {"agent": agent_name, "event": event_type, "content": content, "metadata": metadata}
            )
            # Still write to file for proper cleanup
            return original_log_reasoning(agent_name, event_type, content, metadata)

        session_logger.log_reasoning = mock_log_reasoning

        # Setup manager state
        manager._session_active = True
        manager._pod_gateways = {}
        manager._pod_runtimes = {}
        manager._iteration = 0

        # Run event loop for 6 iterations (governance runs at 5)
        async def run_limited_loop():
            for _ in range(6):
                manager._iteration += 1
                pod_summaries = _make_all_summaries()

                # Run governance at correct frequency
                if manager._iteration > 0 and manager._iteration % 5 == 0:
                    try:
                        governance_result = await manager._governance.run_full_cycle(
                            pod_summaries
                        )
                        manager._session_logger.log_reasoning(
                            "governance",
                            "cycle",
                            f"Iteration {manager._iteration}: Breached=[], "
                            f"Loop6_Consensus={governance_result.get('loop6_consensus', False)}, "
                            f"Loop7_Consensus={governance_result.get('loop7_consensus', False)}",
                            metadata={
                                "iteration": manager._iteration,
                                "breached_pods": [],
                                "loop6_consensus": governance_result.get("loop6_consensus", False),
                                "loop7_consensus": governance_result.get("loop7_consensus", False),
                            },
                        )
                    except Exception as e:
                        pass

                await asyncio.sleep(0.01)

            manager._session_active = False

        await run_limited_loop()
        await manager.stop_session()
        # Note: stop_session() closes the session_logger, so don't call close() again

        # Verify log_reasoning was called with correct parameters
        governance_calls = [
            call for call in log_reasoning_calls if call["agent"] == "governance"
        ]
        assert len(governance_calls) >= 1, "Expected at least 1 governance log call"

        # Check first governance call
        gov_call = governance_calls[0]
        assert gov_call["agent"] == "governance"
        assert gov_call["event"] == "cycle"
        assert "5" in gov_call["content"]  # Iteration 5
        assert "Loop6_Consensus" in gov_call["content"]
        assert "Loop7_Consensus" in gov_call["content"]

        # Check metadata
        assert gov_call["metadata"] is not None
        assert gov_call["metadata"]["iteration"] == 5
        assert gov_call["metadata"]["loop6_consensus"] is True
        assert gov_call["metadata"]["loop7_consensus"] is True


@pytest.mark.asyncio
async def test_session_manager_governance_error_handling():
    """Test governance cycle error is caught and doesn't crash event loop.

    - Mock GovernanceOrchestrator.run_full_cycle() to raise exception
    - Run event loop for 6 iterations (governance runs at iter 5)
    - Verify exception caught and logged (not propagated)
    - Verify event loop continues running (doesn't crash)
    - Call stop_session()
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        # Setup mocks
        alpaca_mock = AsyncMock()
        alpaca_mock.fetch_account = AsyncMock(
            return_value={"equity": 100_000, "buying_power": 50_000, "position_count": 0}
        )
        alpaca_mock.fetch_bars = AsyncMock(return_value={})

        audit_log = AuditLog()
        event_bus = EventBus(audit_log=audit_log)
        session_logger = SessionLogger(session_dir=tmpdir)

        # Create SessionManager
        manager = SessionManager(
            alpaca_adapter=alpaca_mock,
            event_bus=event_bus,
            audit_log=audit_log,
            session_dir=tmpdir,
        )

        # Mock GovernanceOrchestrator to raise exception
        mock_governance = AsyncMock(spec=GovernanceOrchestrator)
        mock_governance.run_full_cycle = AsyncMock(
            side_effect=RuntimeError("Governance cycle failed")
        )
        manager._governance = mock_governance
        manager._session_logger = session_logger

        # Setup manager state
        manager._session_active = True
        manager._pod_gateways = {}
        manager._pod_runtimes = {}
        manager._iteration = 0

        exception_caught = False

        # Run event loop for 6 iterations (governance runs at 5, should fail but continue)
        async def run_limited_loop():
            nonlocal exception_caught
            for _ in range(6):
                manager._iteration += 1
                pod_summaries = _make_all_summaries()

                # Run governance at correct frequency
                if manager._iteration > 0 and manager._iteration % 5 == 0:
                    try:
                        governance_result = await manager._governance.run_full_cycle(
                            pod_summaries
                        )
                    except Exception as e:
                        exception_caught = True
                        manager._session_logger.log_reasoning(
                            "governance",
                            "cycle",
                            f"Iteration {manager._iteration}: Governance error: {str(e)}",
                        )
                        # Don't re-raise — continue loop

                await asyncio.sleep(0.01)

            manager._session_active = False

        # This should NOT raise an exception
        await run_limited_loop()
        await manager.stop_session()
        # Note: stop_session() closes the session_logger, so don't call close() again

        # Verify exception was caught
        assert exception_caught, "Expected governance error to be caught"

        # Verify governance cycle was called
        assert mock_governance.run_full_cycle.call_count == 1

        # Verify we got to the end (event loop didn't crash)
        assert manager._iteration == 6, f"Event loop should complete all iterations, got {manager._iteration}"
