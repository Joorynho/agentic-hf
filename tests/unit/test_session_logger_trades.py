"""Unit tests for SessionLogger trade logging (Phase 1.5)."""

import json
import os
import pytest
import tempfile
from datetime import datetime, timezone

from src.mission_control.session_logger import SessionLogger


@pytest.fixture
def temp_session_dir():
    """Create a temporary directory for test logs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


class TestSessionLoggerTradeLogging:
    """Tests for logging trade executions to trades.jsonl."""

    def test_log_trade_with_order_info_dict(self, temp_session_dir):
        """Test logging trade using order_info dict (Task 1.5 method)."""
        logger = SessionLogger(session_dir=temp_session_dir)

        logger.log_trade(
            pod_id="alpha",
            order_info={
                "order_id": "order_123",
                "symbol": "AAPL",
                "side": "BUY",
                "qty": 100.0,
                "fill_price": 150.5,
                "notional": 15050.0,
                "timestamp": "2026-03-06T10:15:30Z",
                "status": "FILLED",
            },
        )

        logger.close()

        # Read trades.jsonl and verify
        trades_file = os.path.join(temp_session_dir, "trades.jsonl")
        assert os.path.exists(trades_file)

        with open(trades_file, "r") as f:
            line = f.readline()
            trade = json.loads(line)

        assert trade["pod_id"] == "alpha"
        assert trade["order_id"] == "order_123"
        assert trade["symbol"] == "AAPL"
        assert trade["side"] == "BUY"
        assert trade["qty"] == 100.0
        assert trade["fill_price"] == 150.5
        assert trade["notional"] == 15050.0
        assert trade["status"] == "FILLED"

    def test_log_trade_with_individual_args(self, temp_session_dir):
        """Test logging trade using individual arguments (legacy method)."""
        logger = SessionLogger(session_dir=temp_session_dir)

        logger.log_trade(
            pod_id="beta",
            order_id="order_456",
            symbol="MSFT",
            side="SELL",
            qty=50.0,
            filled_price=300.0,
            status="FILLED",
        )

        logger.close()

        # Read trades.jsonl and verify
        trades_file = os.path.join(temp_session_dir, "trades.jsonl")
        with open(trades_file, "r") as f:
            line = f.readline()
            trade = json.loads(line)

        assert trade["pod_id"] == "beta"
        assert trade["order_id"] == "order_456"
        assert trade["symbol"] == "MSFT"
        assert trade["side"] == "SELL"
        assert trade["qty"] == 50.0
        assert trade["filled_price"] == 300.0
        assert trade["status"] == "FILLED"

    def test_log_multiple_trades(self, temp_session_dir):
        """Test logging multiple trades in sequence."""
        logger = SessionLogger(session_dir=temp_session_dir)

        # Log 3 trades
        logger.log_trade(
            pod_id="alpha",
            order_info={
                "order_id": "order_1",
                "symbol": "AAPL",
                "side": "BUY",
                "qty": 10.0,
                "fill_price": 150.5,
                "notional": 1505.0,
                "status": "FILLED",
            },
        )
        logger.log_trade(
            pod_id="beta",
            order_info={
                "order_id": "order_2",
                "symbol": "MSFT",
                "side": "SELL",
                "qty": 5.0,
                "fill_price": 300.0,
                "notional": 1500.0,
                "status": "FILLED",
            },
        )
        logger.log_trade(
            pod_id="alpha",
            order_info={
                "order_id": "order_3",
                "symbol": "AAPL",
                "side": "SELL",
                "qty": 10.0,
                "fill_price": 151.0,
                "notional": 1510.0,
                "status": "FILLED",
            },
        )

        logger.close()

        # Read trades.jsonl and verify count
        trades_file = os.path.join(temp_session_dir, "trades.jsonl")
        with open(trades_file, "r") as f:
            lines = f.readlines()
            assert len(lines) == 3

            trade1 = json.loads(lines[0])
            assert trade1["symbol"] == "AAPL"
            assert trade1["qty"] == 10.0

            trade2 = json.loads(lines[1])
            assert trade2["symbol"] == "MSFT"

            trade3 = json.loads(lines[2])
            assert trade3["pod_id"] == "alpha"

    def test_trades_jsonl_includes_all_required_fields(self, temp_session_dir):
        """Verify trades.jsonl entries have all required fields."""
        logger = SessionLogger(session_dir=temp_session_dir)

        logger.log_trade(
            pod_id="gamma",
            order_info={
                "order_id": "order_789",
                "symbol": "GOOGL",
                "side": "BUY",
                "qty": 100.0,
                "fill_price": 140.0,
                "notional": 14000.0,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "mandate_applied": True,
                "risk_approved": True,
                "status": "FILLED",
            },
        )

        logger.close()

        trades_file = os.path.join(temp_session_dir, "trades.jsonl")
        with open(trades_file, "r") as f:
            trade = json.loads(f.readline())

        # Check required fields
        required_fields = [
            "timestamp",
            "pod_id",
            "order_id",
            "symbol",
            "side",
            "qty",
            "fill_price",
            "notional",
            "status",
        ]
        for field in required_fields:
            assert field in trade, f"Missing required field: {field}"

        # Check optional audit fields
        assert trade.get("mandate_applied") == True
        assert trade.get("risk_approved") == True

    def test_session_markdown_includes_trade_entries(self, temp_session_dir):
        """Verify session.md includes human-readable trade entries."""
        logger = SessionLogger(session_dir=temp_session_dir)

        logger.log_trade(
            pod_id="delta",
            order_info={
                "order_id": "order_delta_1",
                "symbol": "TSLA",
                "side": "BUY",
                "qty": 25.0,
                "fill_price": 200.0,
                "notional": 5000.0,
                "status": "FILLED",
            },
        )

        logger.close()

        markdown_file = os.path.join(temp_session_dir, "session.md")
        with open(markdown_file, "r") as f:
            content = f.read()

        # Should contain trade summary
        assert "TRADE" in content
        assert "delta" in content
        assert "TSLA" in content
        assert "BUY" in content
        assert "25" in content

    def test_session_summary_includes_trade_count(self, temp_session_dir):
        """Verify session.md summary includes trade count and volume."""
        logger = SessionLogger(session_dir=temp_session_dir)

        # Log 3 trades
        for i in range(3):
            logger.log_trade(
                pod_id="epsilon",
                order_info={
                    "order_id": f"order_{i}",
                    "symbol": "NVDA",
                    "side": "BUY",
                    "qty": 10.0,
                    "fill_price": 100.0,
                    "notional": 1000.0,
                    "status": "FILLED",
                },
            )

        logger.close()

        markdown_file = os.path.join(temp_session_dir, "session.md")
        with open(markdown_file, "r") as f:
            content = f.read()

        # Should contain summary section
        assert "Session Summary" in content
        assert "Total trades executed:" in content
        assert "3" in content
        assert "Total notional volume:" in content
        # 3 trades * $1000 = $3000
        assert "3000" in content or "$3,000" in content

    def test_log_trade_timestamp_default(self, temp_session_dir):
        """Test that timestamp defaults to now if not provided."""
        logger = SessionLogger(session_dir=temp_session_dir)

        logger.log_trade(
            pod_id="alpha",
            order_id="order_no_ts",
            symbol="AAPL",
            side="BUY",
            qty=10.0,
            filled_price=150.0,
        )

        logger.close()

        trades_file = os.path.join(temp_session_dir, "trades.jsonl")
        with open(trades_file, "r") as f:
            trade = json.loads(f.readline())

        assert trade["timestamp"] is not None
        # Should be a valid ISO format timestamp
        datetime.fromisoformat(trade["timestamp"].replace("Z", "+00:00"))

    def test_log_trade_with_partial_fill(self, temp_session_dir):
        """Test logging a partial fill."""
        logger = SessionLogger(session_dir=temp_session_dir)

        logger.log_trade(
            pod_id="beta",
            order_info={
                "order_id": "partial_order",
                "symbol": "MSFT",
                "side": "BUY",
                "qty": 50.0,  # Only 50 of 100 filled
                "fill_price": 300.0,
                "notional": 15000.0,
                "status": "PARTIAL",
            },
        )

        logger.close()

        trades_file = os.path.join(temp_session_dir, "trades.jsonl")
        with open(trades_file, "r") as f:
            trade = json.loads(f.readline())

        assert trade["status"] == "PARTIAL"
        assert trade["qty"] == 50.0

    def test_fill_log_in_memory_for_summary(self, temp_session_dir):
        """Test that _fill_log maintains in-memory copy for summary stats."""
        logger = SessionLogger(session_dir=temp_session_dir)

        logger.log_trade(
            pod_id="alpha",
            order_info={
                "order_id": "order_1",
                "symbol": "AAPL",
                "side": "BUY",
                "qty": 10.0,
                "fill_price": 150.0,
                "notional": 1500.0,
                "status": "FILLED",
            },
        )
        logger.log_trade(
            pod_id="beta",
            order_info={
                "order_id": "order_2",
                "symbol": "MSFT",
                "side": "SELL",
                "qty": 5.0,
                "fill_price": 300.0,
                "notional": 1500.0,
                "status": "FILLED",
            },
        )

        # Check in-memory log before close
        assert len(logger._fill_log) == 2
        assert logger._fill_log[0]["order_id"] == "order_1"
        assert logger._fill_log[1]["order_id"] == "order_2"

        logger.close()

    def test_notional_calculation_in_log(self, temp_session_dir):
        """Test that notional is calculated and logged correctly."""
        logger = SessionLogger(session_dir=temp_session_dir)

        qty = 100.0
        price = 150.0
        expected_notional = qty * price

        logger.log_trade(
            pod_id="delta",
            order_info={
                "order_id": "calc_test",
                "symbol": "AAPL",
                "side": "BUY",
                "qty": qty,
                "fill_price": price,
                "notional": expected_notional,
                "status": "FILLED",
            },
        )

        logger.close()

        trades_file = os.path.join(temp_session_dir, "trades.jsonl")
        with open(trades_file, "r") as f:
            trade = json.loads(f.readline())

        assert trade["notional"] == 15000.0
        assert trade["qty"] * trade["fill_price"] == trade["notional"]

    def test_multiple_pods_trading(self, temp_session_dir):
        """Test logging trades from multiple pods simultaneously."""
        logger = SessionLogger(session_dir=temp_session_dir)

        pods = ["alpha", "beta", "gamma", "delta", "epsilon"]
        for i, pod_id in enumerate(pods):
            logger.log_trade(
                pod_id=pod_id,
                order_info={
                    "order_id": f"order_{i}",
                    "symbol": "AAPL",
                    "side": "BUY" if i % 2 == 0 else "SELL",
                    "qty": 10.0,
                    "fill_price": 150.0,
                    "notional": 1500.0,
                    "status": "FILLED",
                },
            )

        logger.close()

        # Verify all trades logged
        trades_file = os.path.join(temp_session_dir, "trades.jsonl")
        with open(trades_file, "r") as f:
            lines = f.readlines()
            assert len(lines) == 5

            for i, line in enumerate(lines):
                trade = json.loads(line)
                assert trade["pod_id"] in pods

    def test_trades_jsonl_jsonl_format(self, temp_session_dir):
        """Verify trades.jsonl uses JSONL format (one JSON per line)."""
        logger = SessionLogger(session_dir=temp_session_dir)

        # Log multiple trades
        for i in range(3):
            logger.log_trade(
                pod_id="test",
                order_info={
                    "order_id": f"order_{i}",
                    "symbol": "TEST",
                    "side": "BUY",
                    "qty": 1.0,
                    "fill_price": 100.0,
                    "notional": 100.0,
                    "status": "FILLED",
                },
            )

        logger.close()

        trades_file = os.path.join(temp_session_dir, "trades.jsonl")
        with open(trades_file, "r") as f:
            lines = f.readlines()
            assert len(lines) == 3

            # Each line should be valid JSON
            for line in lines:
                trade = json.loads(line)
                assert isinstance(trade, dict)
                assert "pod_id" in trade
