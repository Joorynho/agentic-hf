"""MVP3 Batch 4 tests — Bar distribution flow in SessionManager.run_event_loop()."""
from __future__ import annotations

import asyncio
import shutil
import tempfile
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.config.universes import POD_UNIVERSES
from src.core.models.market import Bar
from src.core.models.pod_summary import PodRiskMetrics, PodSummary, PodExposureBucket
from src.core.models.enums import PodStatus
from src.execution.paper.alpaca_adapter import AlpacaAdapter
from src.mission_control.session_manager import SessionManager


def _make_bars_for_symbols(symbols, now=None):
    """Create bar dict for given symbols (used by dynamic mock)."""
    now = now or datetime.now(timezone.utc)
    return {
        s: [Bar(symbol=s, timestamp=now, open=100.0, high=101.0, low=99.0, close=100.5, volume=1000, source="alpaca")]
        for s in symbols
    }


# ============================================================================
# Test 1: Fetch bars from AlpacaAdapter
# ============================================================================


@pytest.mark.asyncio
async def test_session_manager_fetches_bars_from_alpaca():
    """SessionManager.run_event_loop() fetches bars from AlpacaAdapter per-pod universe with 1Hour timeframe."""
    now = datetime.now(timezone.utc)

    async def mock_fetch_bars(symbols, timeframe="1Hour"):
        return _make_bars_for_symbols(symbols, now)

    mock_alpaca = AsyncMock(spec=AlpacaAdapter)
    mock_alpaca.fetch_account = AsyncMock(
        return_value={"equity": 50000.0, "buying_power": 25000.0, "position_count": 0}
    )
    mock_alpaca.fetch_bars = AsyncMock(side_effect=mock_fetch_bars)

    with tempfile.TemporaryDirectory() as tmpdir:
        manager = SessionManager(
            alpaca_adapter=mock_alpaca,
            session_dir=tmpdir,
        )

        await manager.start_live_session(capital_per_pod=100.0)
        assert manager._session_active

        for runtime in manager._pod_runtimes.values():
            runtime.run_cycle = AsyncMock(return_value=None)
            if hasattr(runtime, '_researcher') and runtime._researcher:
                runtime._researcher.run_cycle = AsyncMock(return_value={})

        loop_task = asyncio.create_task(manager.run_event_loop(interval_seconds=0.01, governance_freq=100))
        await asyncio.sleep(0.3)
        await manager.stop_session()

        assert mock_alpaca.fetch_bars.called, "fetch_bars should have been called"
        assert len(mock_alpaca.fetch_bars.call_args_list) >= 2, \
            f"Expected at least 2 calls (start_live_session + run_event_loop), got {len(mock_alpaca.fetch_bars.call_args_list)}"

        event_loop_call = None
        for call_args in mock_alpaca.fetch_bars.call_args_list:
            symbols_arg = call_args[0][0]
            if "AAPL" in symbols_arg:
                event_loop_call = call_args
                break

        assert event_loop_call is not None, \
            "Could not find run_event_loop fetch_bars call (equities universe should contain AAPL)"

        symbols_arg = event_loop_call[0][0]
        assert "AAPL" in symbols_arg, f"Equities universe should include AAPL, got {symbols_arg[:5]}..."

        timeframe_arg = event_loop_call[1].get("timeframe", "1Min")
        assert timeframe_arg == "1Hour", f"Expected timeframe '1Hour', got {timeframe_arg}"

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
    """SessionManager.run_event_loop() pushes bars to all pod gateways (per-pod universe)."""
    now = datetime.now(timezone.utc)

    async def mock_fetch_bars(symbols, timeframe="1Hour"):
        return _make_bars_for_symbols(symbols, now)

    mock_alpaca = AsyncMock(spec=AlpacaAdapter)
    mock_alpaca.fetch_account = AsyncMock(
        return_value={"equity": 50000.0, "buying_power": 25000.0, "position_count": 0}
    )
    mock_alpaca.fetch_bars = AsyncMock(side_effect=mock_fetch_bars)

    with tempfile.TemporaryDirectory() as tmpdir:
        manager = SessionManager(
            alpaca_adapter=mock_alpaca,
            session_dir=tmpdir,
        )

        await manager.start_live_session(capital_per_pod=100.0)
        assert manager._session_active

        for pod_id, gateway in manager._pod_gateways.items():
            gateway.push_bar = AsyncMock()

        for runtime in manager._pod_runtimes.values():
            runtime.run_cycle = AsyncMock(return_value=None)
            if hasattr(runtime, '_researcher') and runtime._researcher:
                runtime._researcher.run_cycle = AsyncMock(return_value={})

        loop_task = asyncio.create_task(manager.run_event_loop(interval_seconds=0.01, governance_freq=100))
        await asyncio.sleep(0.3)
        await manager.stop_session()

        for pod_id, gateway in manager._pod_gateways.items():
            assert gateway.push_bar.called, f"push_bar should have been called for pod {pod_id}"

            pod_symbols = set(POD_UNIVERSES.get(pod_id, []))
            call_count = gateway.push_bar.call_count
            assert call_count >= 1, f"Pod {pod_id} should have received at least 1 bar, got {call_count}"

            pushed_bars = [call[0][0] for call in gateway.push_bar.call_args_list]
            pushed_symbols = {bar.symbol for bar in pushed_bars}
            # Each pod receives bars for its universe (symbols from fetch_bars for that pod)
            assert pushed_symbols.issubset(pod_symbols) or len(pod_symbols) == 0, \
                f"Pod {pod_id} received symbols {pushed_symbols} not in universe (first 5: {list(pod_symbols)[:5]})"

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
    now = datetime.now(timezone.utc)

    async def mock_fetch_bars(symbols, timeframe="1Hour"):
        return _make_bars_for_symbols(symbols, now)

    mock_alpaca = AsyncMock(spec=AlpacaAdapter)
    mock_alpaca.fetch_account = AsyncMock(
        return_value={"equity": 50000.0, "buying_power": 25000.0, "position_count": 0}
    )
    mock_alpaca.fetch_bars = AsyncMock(side_effect=mock_fetch_bars)

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

        for runtime in manager._pod_runtimes.values():
            runtime.run_cycle = AsyncMock(return_value=None)
            if hasattr(runtime, '_researcher') and runtime._researcher:
                runtime._researcher.run_cycle = AsyncMock(return_value={})

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

        for runtime in manager._pod_runtimes.values():
            runtime.run_cycle = AsyncMock(return_value=None)

        # Create a task to run one iteration
        loop_task = asyncio.create_task(manager.run_event_loop(interval_seconds=0.01, governance_freq=100))

        await asyncio.sleep(0.3)

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

        # Verify the number of summaries emitted matches the number of pods (4 pods)
        total_emit_calls = sum(gateway.emit_summary.call_count for gateway in manager._pod_gateways.values())
        assert total_emit_calls >= 4, \
            f"Total emit_summary calls across all pods should be at least 4 (once per pod), got {total_emit_calls}"

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
