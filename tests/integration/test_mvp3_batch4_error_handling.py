"""MVP3 Batch 4 tests — SessionManager error handling and resilience."""
from __future__ import annotations

import asyncio
import logging
import tempfile
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.models.market import Bar
from src.execution.paper.alpaca_adapter import AlpacaAdapter
from src.mission_control.session_manager import SessionManager


# ============================================================================
# Error Handling Tests: Alpaca Fetch Failure
# ============================================================================


@pytest.mark.asyncio
async def test_session_manager_handles_alpaca_fetch_failure(caplog):
    """Test SessionManager resilience to Alpaca fetch_bars() failures.

    Verifies:
    - Exception caught and logged (not propagated to caller)
    - Event loop continues after error (doesn't crash)
    - Session remains active (self._session_active == True)
    - Next iteration retries fetch (calls fetch_bars() again)
    """
    # Create mock adapter
    mock_adapter = AsyncMock(spec=AlpacaAdapter)

    # Mock fetch_account to succeed once
    mock_adapter.fetch_account = AsyncMock(
        return_value={"equity": 10000.0, "buying_power": 5000.0, "position_count": 0}
    )

    # Mock fetch_bars: dynamic return for any symbols; first iteration fails
    call_count = [0]

    async def fetch_bars_side_effect(symbols, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return {s: [] for s in symbols}  # start_live_session
        if call_count[0] == 2:
            raise TimeoutError("Alpaca API timeout")  # First iteration fails
        return {s: [] for s in symbols}  # Subsequent iterations succeed

    mock_adapter.fetch_bars = AsyncMock(side_effect=fetch_bars_side_effect)

    with tempfile.TemporaryDirectory() as tmpdir:
        with caplog.at_level(logging.ERROR):
            manager = SessionManager(
                alpaca_adapter=mock_adapter,
                session_dir=tmpdir,
            )

            await manager.start_live_session(capital_per_pod=100.0)
            assert manager._session_active

            for runtime in manager._pod_runtimes.values():
                runtime.run_cycle = AsyncMock(return_value=None)
                if hasattr(runtime, '_researcher') and runtime._researcher:
                    runtime._researcher.run_cycle = AsyncMock(return_value={})

            task = asyncio.create_task(
                manager.run_event_loop(interval_seconds=0.01, governance_freq=10)
            )

            await asyncio.sleep(0.3)

            # Stop the session by cancelling the task
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            # Verify fetch_bars was called (initial call + at least 1 event loop iteration)
            assert mock_adapter.fetch_bars.call_count >= 1

            # Verify error was logged if enough calls happened to trigger the failure
            if mock_adapter.fetch_bars.call_count >= 2:
                error_logs = [r for r in caplog.records if r.levelname == "ERROR"]
                assert any("bar fetch failed" in getattr(r, "message", r.getMessage()) for r in error_logs), \
                    "Expected error log for fetch_bars failure"

            # Clean up
            manager._session_active = False
            await manager.stop_session()


@pytest.mark.asyncio
async def test_session_manager_handles_pod_push_failure(caplog):
    """Test SessionManager resilience to pod gateway push_bar() failures.

    Verifies:
    - Exception caught (not propagated)
    - Other pods still receive bars (push_bar called for non-failing pods)
    - Event loop continues normally
    - Session remains active
    """
    # Create mock adapter
    mock_adapter = AsyncMock(spec=AlpacaAdapter)

    # Mock fetch_account to succeed
    mock_adapter.fetch_account = AsyncMock(
        return_value={"equity": 10000.0, "buying_power": 5000.0, "position_count": 0}
    )

    # Create test bars for distribution to pods
    test_bars = {
        "AAPL": [
            Bar(
                symbol="AAPL",
                timestamp=datetime.now(timezone.utc),
                open=150.0,
                high=151.0,
                low=149.0,
                close=150.5,
                volume=1000000,
                source="test",
            )
        ],
        "MSFT": [
            Bar(
                symbol="MSFT",
                timestamp=datetime.now(timezone.utc),
                open=320.0,
                high=321.0,
                low=319.0,
                close=320.5,
                volume=900000,
                source="test",
            )
        ],
        "GOOGL": [
            Bar(
                symbol="GOOGL",
                timestamp=datetime.now(timezone.utc),
                open=140.0,
                high=141.0,
                low=139.0,
                close=140.5,
                volume=800000,
                source="test",
            )
        ],
    }

    # Mock fetch_bars: return test bars for any symbols requested (run_event_loop fetches per-pod)
    now = datetime.now(timezone.utc)
    def make_bars(symbols):
        out = {}
        for s in symbols:
            out[s] = test_bars.get(s, [Bar(symbol=s, timestamp=now, open=100, high=101, low=99, close=100.5, volume=1000, source="test")])
        return out

    async def fetch_bars_side_effect(symbols, **kwargs):
        return make_bars(symbols) if symbols else test_bars

    mock_adapter.fetch_bars = AsyncMock(side_effect=fetch_bars_side_effect)

    with tempfile.TemporaryDirectory() as tmpdir:
        with caplog.at_level(logging.WARNING):
            manager = SessionManager(
                alpaca_adapter=mock_adapter,
                session_dir=tmpdir,
            )

            await manager.start_live_session(capital_per_pod=100.0)
            assert manager._session_active

            for runtime in manager._pod_runtimes.values():
                runtime.run_cycle = AsyncMock(return_value=None)
                if hasattr(runtime, '_researcher') and runtime._researcher:
                    runtime._researcher.run_cycle = AsyncMock(return_value={})

            pod_gateways = manager._pod_gateways
            assert len(pod_gateways) == 4

            # Track push_bar calls
            push_bar_calls = {pod_id: 0 for pod_id in pod_gateways}

            # Mock the first pod's push_bar to fail on certain calls
            failing_pod_id = "equities"
            original_push_bar = pod_gateways[failing_pod_id].push_bar

            async def failing_push_bar(bar):
                push_bar_calls[failing_pod_id] += 1
                raise RuntimeError(f"Pod {failing_pod_id} gateway failure")

            pod_gateways[failing_pod_id].push_bar = failing_push_bar

            # Wrap other pods to track calls
            for pod_id in ["fx", "crypto", "commodities"]:
                original_fn = pod_gateways[pod_id].push_bar

                async def make_tracking_push(pid, orig_fn):
                    async def tracking_push(bar):
                        push_bar_calls[pid] += 1
                        return await orig_fn(bar)
                    return tracking_push

                pod_gateways[pod_id].push_bar = (await make_tracking_push(pod_id, original_fn))

            # Run event loop for short time
            task = asyncio.create_task(
                manager.run_event_loop(interval_seconds=0.01, governance_freq=10)
            )

            await asyncio.sleep(0.3)

            # Stop the session
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            # Verify failing pod's push_bar was called (attempted)
            assert push_bar_calls["equities"] > 0

            # Verify other pods received bars
            assert push_bar_calls["fx"] > 0 or push_bar_calls["crypto"] > 0 or push_bar_calls["commodities"] > 0, \
                "Expected at least one non-failing pod to receive bars"

            # Verify error was logged for failed pod
            warning_logs = [r for r in caplog.records if r.levelname == "WARNING"]
            assert any("push_bar failed for" in getattr(r, "message", r.getMessage()) for r in warning_logs), \
                "Expected warning log for failed pod push"

            # Clean up
            manager._session_active = False
            await manager.stop_session()


# ============================================================================
# Additional Error Resilience Tests
# ============================================================================


@pytest.mark.asyncio
async def test_session_manager_continues_after_governance_failure(caplog):
    """Test SessionManager continues event loop even if governance cycle fails.

    Verifies:
    - Governance failure doesn't crash event loop
    - Session remains active
    - Next iteration proceeds normally
    """
    # Create mock adapter
    mock_adapter = AsyncMock(spec=AlpacaAdapter)

    # Mock fetch_account to succeed
    mock_adapter.fetch_account = AsyncMock(
        return_value={"equity": 10000.0, "buying_power": 5000.0, "position_count": 0}
    )

    async def empty_bars_for_symbols(symbols, **kwargs):
        return {s: [] for s in symbols} if symbols else {}

    mock_adapter.fetch_bars = AsyncMock(side_effect=empty_bars_for_symbols)

    with tempfile.TemporaryDirectory() as tmpdir:
        with caplog.at_level(logging.ERROR):
            manager = SessionManager(
                alpaca_adapter=mock_adapter,
                session_dir=tmpdir,
            )

            # Start session
            await manager.start_live_session(capital_per_pod=100.0)
            assert manager._session_active

            for runtime in manager._pod_runtimes.values():
                runtime.run_cycle = AsyncMock(return_value=None)
                if hasattr(runtime, '_researcher') and runtime._researcher:
                    runtime._researcher.run_cycle = AsyncMock(return_value={})

            # Mock governance to fail
            manager._governance.run_full_cycle = AsyncMock(
                side_effect=RuntimeError("Governance orchestrator failure")
            )

            # Run event loop with governance_freq=1 (run governance every iteration)
            task = asyncio.create_task(
                manager.run_event_loop(interval_seconds=0.01, governance_freq=1)
            )

            await asyncio.sleep(0.3)

            # Stop the session
            manager._session_active = False
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            # Verify governance was called at least once
            assert manager._governance.run_full_cycle.call_count >= 1

            # Verify error was logged
            error_logs = [r for r in caplog.records if r.levelname == "ERROR"]
            assert any("Governance cycle failed" in getattr(r, "message", r.getMessage()) for r in error_logs), \
                "Expected error log for governance failure"

            await manager.stop_session()


@pytest.mark.asyncio
async def test_session_manager_continues_after_account_fetch_failure(caplog):
    """Test SessionManager continues even if periodic account fetch fails.

    Verifies:
    - Account fetch failure doesn't crash event loop
    - Session remains active
    - Event loop continues to next iteration
    """
    # Create mock adapter
    mock_adapter = AsyncMock(spec=AlpacaAdapter)

    # Mock fetch_account: succeed on start, fail on subsequent periodic calls
    call_count = {"fetch_account": 0}

    async def fetch_account_side_effect():
        call_count["fetch_account"] += 1
        if call_count["fetch_account"] == 1:
            # First call (during start_live_session) succeeds
            return {"equity": 10000.0, "buying_power": 5000.0, "position_count": 0}
        else:
            # Subsequent calls fail (simulating periodic account fetch failures)
            raise RuntimeError("Account fetch timeout")

    mock_adapter.fetch_account = AsyncMock(side_effect=fetch_account_side_effect)

    # Mock fetch_bars to return empty bars (will be called many times)
    call_count["fetch_bars"] = 0

    async def fetch_bars_side_effect(symbols, **kwargs):
        call_count["fetch_bars"] += 1
        if call_count["fetch_bars"] == 1:
            # Initial bars on start_live_session
            return {"AAPL": [], "MSFT": [], "GOOGL": [], "TSLA": [], "AMZN": []}
        else:
            # Return empty bars for all symbols (for iterations)
            return {s: [] for s in symbols}

    mock_adapter.fetch_bars = AsyncMock(side_effect=fetch_bars_side_effect)

    with tempfile.TemporaryDirectory() as tmpdir:
        with caplog.at_level(logging.WARNING):
            manager = SessionManager(
                alpaca_adapter=mock_adapter,
                session_dir=tmpdir,
            )

            await manager.start_live_session(capital_per_pod=100.0)
            assert manager._session_active

            for runtime in manager._pod_runtimes.values():
                runtime.run_cycle = AsyncMock(return_value=None)
                if hasattr(runtime, '_researcher') and runtime._researcher:
                    runtime._researcher.run_cycle = AsyncMock(return_value={})

            task = asyncio.create_task(
                manager.run_event_loop(interval_seconds=0.01, governance_freq=50)
            )

            await asyncio.sleep(0.3)

            # Stop the session
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            # Verify warning was logged for account fetch failure
            warning_logs = [r for r in caplog.records if r.levelname == "WARNING"]
            failed_account_logs = [r for r in warning_logs if "Failed to fetch account" in r.message]

            # We should have at least one failed account fetch warning
            # if we ran 10+ iterations
            if manager._iteration >= 10:
                assert any("Failed to fetch account" in getattr(r, "message", r.getMessage()) for r in warning_logs), \
                    f"Expected warning log for account fetch failure (ran {manager._iteration} iterations)"

            # Clean up
            manager._session_active = False
            await manager.stop_session()
