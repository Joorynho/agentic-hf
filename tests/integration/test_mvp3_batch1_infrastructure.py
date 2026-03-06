"""MVP3 Batch 1 tests — AlpacaAdapter, SessionLogger, SessionManager smoke tests."""
from __future__ import annotations

import json
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.execution.paper.alpaca_adapter import AlpacaAdapter
from src.mission_control.session_logger import SessionLogger
from src.mission_control.session_manager import SessionManager


# ============================================================================
# AlpacaAdapter Tests
# ============================================================================


def test_alpaca_adapter_init_requires_keys():
    """AlpacaAdapter raises error if API keys not in env."""
    # Clear env keys
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValueError, match="API_KEY.*ALPACA_SECRET_KEY"):
            AlpacaAdapter()


def test_alpaca_adapter_init_with_explicit_keys():
    """AlpacaAdapter initializes with explicit keys."""
    adapter = AlpacaAdapter(api_key="test_key", secret_key="test_secret")
    assert adapter._api_key == "test_key"
    assert adapter._secret_key == "test_secret"


@pytest.mark.asyncio
async def test_alpaca_adapter_fetch_bars_mock():
    """fetch_bars returns dict[symbol] -> list[Bar] structure (mocked)."""
    from datetime import datetime, timezone

    adapter = AlpacaAdapter(api_key="test", secret_key="test")

    # Mock the REST client with properly mocked DataFrames
    mock_barset = {
        "AAPL": MagicMock(),
        "MSFT": MagicMock(),
    }

    # Create a realistic timestamp for the index
    test_timestamp = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

    # Create a mock row that behaves like pandas Series
    mock_row = MagicMock()
    mock_row.__getitem__ = MagicMock(side_effect=lambda k: {
        "open": 150.0,
        "high": 151.0,
        "low": 149.0,
        "close": 150.5,
        "volume": 1000000,
    }[k])

    # Each symbol has a dataframe-like structure (mock rows)
    # Index is the timestamp, row is the Series with OHLCV data
    mock_barset["AAPL"].iterrows = lambda: [(test_timestamp, mock_row)]
    mock_barset["MSFT"].iterrows = lambda: []

    with patch.object(adapter._client, "get_bars", return_value=mock_barset):
        bars = await adapter.fetch_bars(["AAPL", "MSFT"])

    assert "AAPL" in bars
    assert "MSFT" in bars
    assert len(bars["AAPL"]) == 1
    assert bars["AAPL"][0].symbol == "AAPL"
    assert bars["AAPL"][0].close == 150.5


# ============================================================================
# SessionLogger Tests
# ============================================================================


def test_session_logger_init_creates_directory():
    """SessionLogger creates log directory on init."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_dir = f"{tmpdir}/test_session"
        logger = SessionLogger(session_dir=log_dir)
        assert os.path.isdir(log_dir)
        assert os.path.isfile(f"{log_dir}/reasoning.jsonl")
        assert os.path.isfile(f"{log_dir}/conversations.jsonl")
        assert os.path.isfile(f"{log_dir}/trades.jsonl")
        assert os.path.isfile(f"{log_dir}/session.md")
        logger.close()


def test_session_logger_log_reasoning():
    """SessionLogger.log_reasoning writes JSONL entry."""
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = SessionLogger(session_dir=tmpdir)
        logger.log_reasoning("ceo", "prompt", "You are the CEO...")
        logger.close()

        # Read back and verify JSONL
        with open(f"{tmpdir}/reasoning.jsonl", "r") as f:
            lines = f.readlines()
        assert len(lines) >= 1
        entry = json.loads(lines[0])
        assert entry["agent"] == "ceo"
        assert entry["event"] == "prompt"
        assert "You are the CEO" in entry["content"]


def test_session_logger_log_trade():
    """SessionLogger.log_trade writes JSONL entry."""
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = SessionLogger(session_dir=tmpdir)
        logger.log_trade(
            pod_id="alpha",
            order_id="12345",
            symbol="AAPL",
            side="buy",
            qty=10.0,
            filled_price=150.5,
        )
        logger.close()

        # Read back and verify JSONL
        with open(f"{tmpdir}/trades.jsonl", "r") as f:
            lines = f.readlines()
        assert len(lines) >= 1
        entry = json.loads(lines[0])
        assert entry["pod_id"] == "alpha"
        assert entry["symbol"] == "AAPL"
        assert entry["qty"] == 10.0


def test_session_logger_context_manager():
    """SessionLogger works as context manager."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with SessionLogger(session_dir=tmpdir) as logger:
            logger.log_trade(
                pod_id="beta",
                order_id="67890",
                symbol="MSFT",
                side="sell",
                qty=5.0,
                filled_price=320.0,
            )
        # Files should be closed after context exit

        # Verify files exist and have content
        assert os.path.isfile(f"{tmpdir}/trades.jsonl")
        with open(f"{tmpdir}/trades.jsonl", "r") as f:
            assert f.read().strip()  # Non-empty


# ============================================================================
# SessionManager Tests
# ============================================================================


def test_session_manager_init():
    """SessionManager initializes without error."""
    with patch("src.mission_control.session_manager.AlpacaAdapter"):
        manager = SessionManager()
        assert manager._iteration == 0
        assert not manager._session_active


@pytest.mark.asyncio
async def test_session_manager_start_session_requires_api_keys():
    """SessionManager.start_live_session raises error if Alpaca keys missing."""
    manager = SessionManager(
        alpaca_adapter=MagicMock(spec=AlpacaAdapter),
    )
    # Mock fetch_account to simulate missing keys error
    manager._alpaca.fetch_account = AsyncMock(
        side_effect=ValueError("API keys missing")
    )

    with pytest.raises(ValueError, match="API keys"):
        await manager.start_live_session(capital_per_pod=100.0)


@pytest.mark.asyncio
async def test_session_manager_stop_session():
    """SessionManager.stop_session sets active flag to False."""
    manager = SessionManager(
        alpaca_adapter=MagicMock(spec=AlpacaAdapter),
    )
    manager._session_active = True
    await manager.stop_session()
    assert not manager._session_active


# ============================================================================
# Integration: Minimal E2E (Mocked)
# ============================================================================


@pytest.mark.asyncio
async def test_mvp3_batch1_minimal_e2e():
    """Minimal E2E: SessionManager init → fetch bars → log trade."""
    # Mock Alpaca adapter
    mock_adapter = AsyncMock(spec=AlpacaAdapter)
    mock_adapter.fetch_account = AsyncMock(
        return_value={"equity": 10000.0, "buying_power": 5000.0, "position_count": 0}
    )
    mock_adapter.fetch_bars = AsyncMock(return_value={"AAPL": [], "MSFT": []})

    # Create session manager
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = SessionManager(
            alpaca_adapter=mock_adapter,
            session_dir=tmpdir,
        )

        # Start session
        await manager.start_live_session(capital_per_pod=100.0)
        assert manager._session_active

        # Log a trade
        manager.log_trade(
            pod_id="alpha",
            order_id="test_order",
            symbol="AAPL",
            side="buy",
            qty=10.0,
            filled_price=150.0,
        )

        # Stop session
        await manager.stop_session()
        assert not manager._session_active

        # Verify trade was logged
        trades_file = f"{manager.get_session_dir()}/trades.jsonl"
        assert os.path.isfile(trades_file)
        with open(trades_file, "r") as f:
            lines = f.readlines()
        assert len(lines) >= 1
        trade = json.loads(lines[0])
        assert trade["pod_id"] == "alpha"
