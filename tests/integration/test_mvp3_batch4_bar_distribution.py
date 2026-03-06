"""MVP3 Batch 4 tests — Bar distribution flow in SessionManager.run_event_loop()."""
from __future__ import annotations

import asyncio
import shutil
import tempfile
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.models.market import Bar
from src.core.models.pod_summary import PodRiskMetrics, PodSummary, PodExposureBucket
from src.core.models.enums import PodStatus
from src.execution.paper.alpaca_adapter import AlpacaAdapter
from src.mission_control.session_manager import SessionManager


# ============================================================================
# Test 1: Fetch bars from AlpacaAdapter
# ============================================================================


@pytest.mark.asyncio
async def test_session_manager_fetches_bars_from_alpaca():
    """SessionManager.run_event_loop() fetches bars from AlpacaAdapter with correct symbols and timeframe."""
    # Create test bars matching run_event_loop's hardcoded symbols
    now = datetime.now(timezone.utc)
    test_bars = {
        "AAPL": [Bar(symbol="AAPL", timestamp=now, open=150.0, high=151.0, low=149.0, close=150.5, volume=1000, source="alpaca")],
        "MSFT": [Bar(symbol="MSFT", timestamp=now, open=300.0, high=301.0, low=299.0, close=300.5, volume=1000, source="alpaca")],
        "GOOGL": [Bar(symbol="GOOGL", timestamp=now, open=140.0, high=141.0, low=139.0, close=140.5, volume=1000, source="alpaca")],
        "AMZN": [Bar(symbol="AMZN", timestamp=now, open=180.0, high=181.0, low=179.0, close=180.5, volume=1000, source="alpaca")],
        "NVDA": [Bar(symbol="NVDA", timestamp=now, open=875.0, high=876.0, low=874.0, close=875.5, volume=1000, source="alpaca")],
    }

    # Mock AlpacaAdapter
    mock_alpaca = AsyncMock(spec=AlpacaAdapter)
    mock_alpaca.fetch_account = AsyncMock(
        return_value={"equity": 50000.0, "buying_power": 25000.0, "position_count": 0}
    )
    mock_alpaca.fetch_bars = AsyncMock(return_value=test_bars)

    with tempfile.TemporaryDirectory() as tmpdir:
        manager = SessionManager(
            alpaca_adapter=mock_alpaca,
            session_dir=tmpdir,
        )

        # Start session
        await manager.start_live_session(capital_per_pod=100.0)
        assert manager._session_active

        # Create a task to run one iteration of the event loop
        loop_task = asyncio.create_task(manager.run_event_loop(interval_seconds=0.01, governance_freq=100))

        # Let it run for a short time to complete one iteration
        await asyncio.sleep(0.5)

        # Stop the session (which will cancel the loop_task)
        await manager.stop_session()

        # Verify AlpacaAdapter.fetch_bars was called
        assert mock_alpaca.fetch_bars.called, "fetch_bars should have been called"
        assert len(mock_alpaca.fetch_bars.call_args_list) >= 2, \
            f"Expected at least 2 calls (start_live_session + run_event_loop), got {len(mock_alpaca.fetch_bars.call_args_list)}"

        # Find the run_event_loop call (should have "NVDA" symbol since start_live_session uses TSLA)
        # We look for the call with the event loop symbols: ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]
        event_loop_call = None
        for call_args in mock_alpaca.fetch_bars.call_args_list:
            symbols_arg = call_args[0][0]
            if "NVDA" in symbols_arg:
                event_loop_call = call_args
                break

        assert event_loop_call is not None, \
            "Could not find run_event_loop fetch_bars call (should contain NVDA symbol)"

        # Verify correct symbols were passed in the event loop call
        symbols_arg = event_loop_call[0][0]
        assert set(symbols_arg) == {"AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"}, \
            f"Expected symbols AAPL, MSFT, GOOGL, AMZN, NVDA from run_event_loop, got {symbols_arg}"

        # Verify timeframe was correct
        timeframe_arg = event_loop_call[1].get("timeframe", "1Min")
        assert timeframe_arg == "1Min", f"Expected timeframe '1Min', got {timeframe_arg}"

        # Clean up the task
        try:
            loop_task.cancel()
            await loop_task
        except asyncio.CancelledError:
            pass


# ============================================================================
# Test 2: Distribute bars to all pods
# ============================================================================


@pytest.mark.asyncio
async def test_session_manager_distributes_bars_to_all_pods():
    """SessionManager.run_event_loop() pushes bars to all pod gateways."""
    # Create test bars (5 symbols × 1 bar each = 5 bars total)
    # Matches run_event_loop's hardcoded symbols: ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]
    now = datetime.now(timezone.utc)
    test_bars = {
        "AAPL": [Bar(symbol="AAPL", timestamp=now, open=150.0, high=151.0, low=149.0, close=150.5, volume=1000, source="alpaca")],
        "MSFT": [Bar(symbol="MSFT", timestamp=now, open=300.0, high=301.0, low=299.0, close=300.5, volume=1000, source="alpaca")],
        "GOOGL": [Bar(symbol="GOOGL", timestamp=now, open=140.0, high=141.0, low=139.0, close=140.5, volume=1000, source="alpaca")],
        "AMZN": [Bar(symbol="AMZN", timestamp=now, open=180.0, high=181.0, low=179.0, close=180.5, volume=1000, source="alpaca")],
        "NVDA": [Bar(symbol="NVDA", timestamp=now, open=875.0, high=876.0, low=874.0, close=875.5, volume=1000, source="alpaca")],
    }

    # Mock AlpacaAdapter
    mock_alpaca = AsyncMock(spec=AlpacaAdapter)
    mock_alpaca.fetch_account = AsyncMock(
        return_value={"equity": 50000.0, "buying_power": 25000.0, "position_count": 0}
    )
    mock_alpaca.fetch_bars = AsyncMock(return_value=test_bars)

    with tempfile.TemporaryDirectory() as tmpdir:
        manager = SessionManager(
            alpaca_adapter=mock_alpaca,
            session_dir=tmpdir,
        )

        # Start session
        await manager.start_live_session(capital_per_pod=100.0)
        assert manager._session_active

        # Mock push_bar on all pod gateways
        for pod_id, gateway in manager._pod_gateways.items():
            gateway.push_bar = AsyncMock()

        # Create a task to run one iteration
        loop_task = asyncio.create_task(manager.run_event_loop(interval_seconds=0.01, governance_freq=100))

        # Let it run for a short time
        await asyncio.sleep(0.5)

        # Stop the session
        await manager.stop_session()

        # Verify each pod gateway received bars
        for pod_id, gateway in manager._pod_gateways.items():
            assert gateway.push_bar.called, f"push_bar should have been called for pod {pod_id}"

            # Verify at least 5 bars were pushed (one per symbol)
            call_count = gateway.push_bar.call_count
            assert call_count >= 5, \
                f"Pod {pod_id} should have received at least 5 bar pushes (one per symbol), got {call_count}"

            # Verify the bar data matches
            pushed_bars = [call[0][0] for call in gateway.push_bar.call_args_list]
            pushed_symbols = {bar.symbol for bar in pushed_bars}
            assert pushed_symbols == {"AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"}, \
                f"Pod {pod_id} should have received all 5 symbols, got {pushed_symbols}"

        # Clean up the task
        try:
            loop_task.cancel()
            await loop_task
        except asyncio.CancelledError:
            pass


# ============================================================================
# Test 3: Emit pod summaries to EventBus
# ============================================================================


@pytest.mark.asyncio
async def test_session_manager_emits_pod_summaries_to_eventbus():
    """SessionManager.run_event_loop() emits PodSummary to EventBus for each pod."""
    # Create test bars matching run_event_loop's hardcoded symbols
    now = datetime.now(timezone.utc)
    test_bars = {
        "AAPL": [Bar(symbol="AAPL", timestamp=now, open=150.0, high=151.0, low=149.0, close=150.5, volume=1000, source="alpaca")],
        "MSFT": [Bar(symbol="MSFT", timestamp=now, open=300.0, high=301.0, low=299.0, close=300.5, volume=1000, source="alpaca")],
        "GOOGL": [Bar(symbol="GOOGL", timestamp=now, open=140.0, high=141.0, low=139.0, close=140.5, volume=1000, source="alpaca")],
        "AMZN": [Bar(symbol="AMZN", timestamp=now, open=180.0, high=181.0, low=179.0, close=180.5, volume=1000, source="alpaca")],
        "NVDA": [Bar(symbol="NVDA", timestamp=now, open=875.0, high=876.0, low=874.0, close=875.5, volume=1000, source="alpaca")],
    }

    # Mock AlpacaAdapter
    mock_alpaca = AsyncMock(spec=AlpacaAdapter)
    mock_alpaca.fetch_account = AsyncMock(
        return_value={"equity": 50000.0, "buying_power": 25000.0, "position_count": 0}
    )
    mock_alpaca.fetch_bars = AsyncMock(return_value=test_bars)

    # Use tmpdir fixture approach
    tmpdir = tempfile.mkdtemp()
    manager = None
    try:
        manager = SessionManager(
            alpaca_adapter=mock_alpaca,
            session_dir=tmpdir,
        )

        # Start session
        await manager.start_live_session(capital_per_pod=100.0)
        assert manager._session_active

        # Mock EventBus.emit (publish method)
        manager._event_bus.publish = AsyncMock()

        # Create test PodSummary for each pod
        test_summaries = {}
        for pod_id in manager._pod_gateways.keys():
            summary = PodSummary(
                pod_id=pod_id,
                timestamp=now,
                status=PodStatus.ACTIVE,
                risk_metrics=PodRiskMetrics(
                    pod_id=pod_id,
                    timestamp=now,
                    nav=100.0,
                    daily_pnl=5.0,
                    drawdown_from_hwm=0.0,
                    current_vol_ann=0.10,
                    gross_leverage=1.0,
                    net_leverage=1.0,
                    var_95_1d=0.025,
                    es_95_1d=0.035,
                ),
                exposure_buckets=[
                    PodExposureBucket(asset_class="equity", direction="long", notional_pct_nav=0.5)
                ],
                expected_return_estimate=0.15,
                turnover_daily_pct=0.05,
                heartbeat_ok=True,
            )
            test_summaries[pod_id] = summary

        # Mock _collect_pod_summaries to return our test summaries
        async def mock_collect_summaries():
            return test_summaries

        manager._collect_pod_summaries = mock_collect_summaries

        # Mock emit_summary on gateways
        for pod_id, gateway in manager._pod_gateways.items():
            gateway.emit_summary = AsyncMock()

        # Create a task to run one iteration
        loop_task = asyncio.create_task(manager.run_event_loop(interval_seconds=0.01, governance_freq=100))

        # Let it run for a short time
        await asyncio.sleep(0.5)

        # Stop the session
        await manager.stop_session()

        # Give file handles time to close (important on Windows with file locks)
        await asyncio.sleep(0.2)

        # Verify each pod gateway emitted a summary
        for pod_id, gateway in manager._pod_gateways.items():
            assert gateway.emit_summary.called, \
                f"emit_summary should have been called for pod {pod_id}"

            # Verify the summary data
            call_args = gateway.emit_summary.call_args_list[0]
            emitted_summary = call_args[0][0]

            assert emitted_summary.pod_id == pod_id, \
                f"Summary pod_id should be {pod_id}, got {emitted_summary.pod_id}"
            assert emitted_summary.nav == 100.0, \
                f"Summary nav should be 100.0, got {emitted_summary.nav}"
            assert emitted_summary.risk_metrics.pod_id == pod_id, \
                f"Summary risk_metrics.pod_id should be {pod_id}"

        # Verify the number of summaries emitted matches the number of pods
        # Each pod gateway should emit at least once per event loop iteration
        total_emit_calls = sum(gateway.emit_summary.call_count for gateway in manager._pod_gateways.values())
        assert total_emit_calls >= 5, \
            f"Total emit_summary calls across all pods should be at least 5 (once per pod), got {total_emit_calls}"

        # Clean up the task
        try:
            loop_task.cancel()
            await loop_task
        except asyncio.CancelledError:
            pass
    finally:
        # Ensure proper cleanup
        if manager:
            try:
                manager._session_logger.close()
                await asyncio.sleep(0.2)
            except Exception:
                pass
        # Clean up tmpdir
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass
