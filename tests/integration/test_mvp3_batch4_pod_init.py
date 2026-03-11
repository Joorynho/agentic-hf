"""MVP3 Batch 4 tests — Pod initialization in SessionManager.

Tests cover:
1. Initialization of 4 pods with correct IDs (equities, fx, crypto, commodities)
2. Capital allocation across pods
3. Agent setup in each pod runtime
"""
from __future__ import annotations

import tempfile
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.governance.governance_orchestrator import GovernanceOrchestrator
from src.execution.paper.alpaca_adapter import AlpacaAdapter
from src.mission_control.session_manager import SessionManager
from src.pods.base.gateway import PodGateway
from src.pods.runtime.pod_runtime import PodRuntime


# ============================================================================
# Test 1: Session Manager Initializes 4 Pods
# ============================================================================


@pytest.mark.asyncio
async def test_session_manager_initializes_5_pods():
    """SessionManager.start_live_session initializes exactly 4 pods with correct IDs.

    Verifies:
    - len(self._pod_gateways) == 4
    - Pod IDs are ["equities", "fx", "crypto", "commodities"]
    - Each pod gateway is a PodGateway instance
    - No runtime errors
    """
    # Mock Alpaca adapter
    mock_adapter = AsyncMock(spec=AlpacaAdapter)
    mock_adapter.fetch_account = AsyncMock(
        return_value={"equity": 10000.0, "buying_power": 5000.0, "position_count": 0}
    )
    mock_adapter.fetch_bars = AsyncMock(return_value={"AAPL": [], "MSFT": []})

    # Create session manager with mocked adapter
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = SessionManager(
            alpaca_adapter=mock_adapter,
            session_dir=tmpdir,
        )

        # Start live session
        await manager.start_live_session(capital_per_pod=100.0)

        # Verify 4 pods initialized
        assert len(manager._pod_gateways) == 4, f"Expected 4 pods, got {len(manager._pod_gateways)}"

        # Verify pod IDs are correct
        expected_pod_ids = ["equities", "fx", "crypto", "commodities"]
        actual_pod_ids = list(manager._pod_gateways.keys())
        assert sorted(actual_pod_ids) == sorted(expected_pod_ids), \
            f"Expected pod IDs {expected_pod_ids}, got {actual_pod_ids}"

        # Verify each pod gateway is a PodGateway instance
        for pod_id, gateway in manager._pod_gateways.items():
            assert isinstance(gateway, PodGateway), \
                f"Pod {pod_id} gateway is {type(gateway)}, expected PodGateway"

        # Verify each pod runtime is a PodRuntime instance
        for pod_id, runtime in manager._pod_runtimes.items():
            assert isinstance(runtime, PodRuntime), \
                f"Pod {pod_id} runtime is {type(runtime)}, expected PodRuntime"

        # Clean up
        await manager.stop_session()


# ============================================================================
# Test 2: Capital Allocation Across Pods
# ============================================================================


@pytest.mark.asyncio
async def test_session_manager_pod_capital_allocation():
    """SessionManager allocates capital equally across 4 pods.

    Verifies:
    - CapitalAllocator initialized
    - Total capital = 4 × capital_per_pod
    - Each pod gets 25% allocation (1.0 / 4 = 0.25)
    - Capital dict has exactly 4 entries
    """
    # Mock Alpaca adapter
    mock_adapter = AsyncMock(spec=AlpacaAdapter)
    mock_adapter.fetch_account = AsyncMock(
        return_value={"equity": 10000.0, "buying_power": 5000.0, "position_count": 0}
    )
    mock_adapter.fetch_bars = AsyncMock(return_value={"AAPL": [], "MSFT": []})

    capital_per_pod = 50.0
    expected_total = 4 * capital_per_pod  # $200

    with tempfile.TemporaryDirectory() as tmpdir:
        manager = SessionManager(
            alpaca_adapter=mock_adapter,
            session_dir=tmpdir,
        )

        # Start session
        await manager.start_live_session(capital_per_pod=capital_per_pod)

        # Verify CapitalAllocator was initialized
        assert manager._allocator is not None, "CapitalAllocator not initialized"

        # Verify capital dict has 4 entries
        assert len(manager._pod_capital) == 4, \
            f"Expected 4 capital entries, got {len(manager._pod_capital)}"

        # Verify each pod has correct capital amount
        for pod_id, capital in manager._pod_capital.items():
            assert capital == capital_per_pod, \
                f"Pod {pod_id} capital is ${capital}, expected ${capital_per_pod}"

        # Verify allocations sum to 1.0 (equal distribution)
        allocations = manager._allocator.current_allocations()
        assert len(allocations) == 4, f"Expected 4 allocations, got {len(allocations)}"

        # Each pod should get 25% (1.0 / 4 = 0.25)
        for pod_id, alloc in allocations.items():
            expected_alloc = round(1.0 / 4, 6)
            assert abs(alloc - expected_alloc) < 0.0001, \
                f"Pod {pod_id} allocation {alloc} != expected {expected_alloc}"

        # Verify total allocation sums to 1.0
        total_alloc = sum(allocations.values())
        assert abs(total_alloc - 1.0) < 0.001, \
            f"Total allocation {total_alloc} != 1.0"

        # Clean up
        await manager.stop_session()


# ============================================================================
# Test 3: Pod Agents Initialized
# ============================================================================


@pytest.mark.asyncio
async def test_session_manager_pod_agents_initialized():
    """SessionManager initializes 6 agents per pod and governance orchestrator.

    Verifies:
    - Each pod runtime has 6 agents set (researcher, signal, pm, risk, exec_trader, ops)
    - GovernanceOrchestrator initialized with CEO, CIO, CRO agents
    - No runtime errors during agent setup
    """
    # Mock Alpaca adapter
    mock_adapter = AsyncMock(spec=AlpacaAdapter)
    mock_adapter.fetch_account = AsyncMock(
        return_value={"equity": 10000.0, "buying_power": 5000.0, "position_count": 0}
    )
    mock_adapter.fetch_bars = AsyncMock(return_value={"AAPL": [], "MSFT": []})

    with tempfile.TemporaryDirectory() as tmpdir:
        manager = SessionManager(
            alpaca_adapter=mock_adapter,
            session_dir=tmpdir,
        )

        # Start session
        await manager.start_live_session(capital_per_pod=100.0)

        # Verify each pod runtime has agents set
        for pod_id, runtime in manager._pod_runtimes.items():
            # Check that all 6 agent attributes are not None (they were injected)
            assert runtime._researcher is not None, f"Pod {pod_id}: researcher not set"
            assert runtime._signal is not None, f"Pod {pod_id}: signal not set"
            assert runtime._pm is not None, f"Pod {pod_id}: pm not set"
            assert runtime._risk is not None, f"Pod {pod_id}: risk not set"
            assert runtime._exec_trader is not None, f"Pod {pod_id}: exec_trader not set"
            assert runtime._ops is not None, f"Pod {pod_id}: ops not set"

        # Verify GovernanceOrchestrator initialized
        assert manager._governance is not None, "GovernanceOrchestrator not initialized"
        assert isinstance(manager._governance, GovernanceOrchestrator), \
            f"Governance is {type(manager._governance)}, expected GovernanceOrchestrator"

        # Verify governance has CEO, CIO, CRO agents
        assert manager._governance._ceo is not None, "CEO agent not set"
        assert manager._governance._cio is not None, "CIO agent not set"
        assert manager._governance._cro is not None, "CRO agent not set"

        # Clean up
        await manager.stop_session()
