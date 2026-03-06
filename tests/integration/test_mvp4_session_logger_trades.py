"""Integration test for Phase 1.5: SessionLogger trade logging with ExecutionTrader."""

import json
import os
import pytest
import tempfile
from datetime import datetime, timezone

from src.mission_control.session_logger import SessionLogger
from src.core.models.execution import Order, OrderResult, RiskApprovalToken
from src.core.models.enums import Side, OrderType


class TestSessionLoggerIntegration:
    """Integration tests for SessionLogger with mock trade data."""

    def test_log_trade_from_order_result(self):
        """Test logging a trade using OrderResult model (from ExecutionTrader)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = SessionLogger(session_dir=tmpdir)

            # Simulate an OrderResult from ExecutionTrader
            order_result = OrderResult(
                order_id="order_exec_test",
                symbol="AAPL",
                qty=100.0,
                side="buy",
                status="FILLED",
                fill_price=150.5,
                fill_qty=100.0,
                filled_at=datetime.now(timezone.utc),
            )

            # Log the trade as SessionManager would do
            logger.log_trade(
                pod_id="alpha",
                order_info={
                    "order_id": order_result.order_id,
                    "symbol": order_result.symbol,
                    "side": order_result.side,
                    "qty": order_result.fill_qty,
                    "fill_price": order_result.fill_price,
                    "notional": order_result.fill_qty * order_result.fill_price,
                    "timestamp": order_result.filled_at.isoformat(),
                    "status": order_result.status,
                },
            )

            logger.close()

            # Verify the trade was logged
            trades_file = os.path.join(tmpdir, "trades.jsonl")
            with open(trades_file, "r") as f:
                trade = json.loads(f.readline())

            assert trade["order_id"] == "order_exec_test"
            assert trade["symbol"] == "AAPL"
            assert trade["side"] == "buy"  # Lowercase as stored
            assert trade["qty"] == 100.0
            assert trade["fill_price"] == 150.5

    def test_multiple_pods_multiple_trades(self):
        """Test logging trades from multiple pods with various symbols."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = SessionLogger(session_dir=tmpdir)

            # Simulate trading across 5 pods
            trades_data = [
                {"pod": "alpha", "symbol": "AAPL", "side": "BUY", "qty": 100, "price": 150.0},
                {"pod": "beta", "symbol": "MSFT", "side": "SELL", "qty": 50, "price": 300.0},
                {"pod": "gamma", "symbol": "GOOGL", "side": "BUY", "qty": 75, "price": 140.0},
                {"pod": "delta", "symbol": "TSLA", "side": "BUY", "qty": 25, "price": 200.0},
                {"pod": "epsilon", "symbol": "NVDA", "side": "SELL", "qty": 60, "price": 120.0},
            ]

            for i, trade_spec in enumerate(trades_data):
                logger.log_trade(
                    pod_id=trade_spec["pod"],
                    order_info={
                        "order_id": f"order_{i}",
                        "symbol": trade_spec["symbol"],
                        "side": trade_spec["side"],
                        "qty": float(trade_spec["qty"]),
                        "fill_price": trade_spec["price"],
                        "notional": float(trade_spec["qty"]) * trade_spec["price"],
                        "status": "FILLED",
                    },
                )

            logger.close()

            # Verify all trades logged and count
            trades_file = os.path.join(tmpdir, "trades.jsonl")
            with open(trades_file, "r") as f:
                lines = f.readlines()
                assert len(lines) == 5

                # Check specific trades
                trades = [json.loads(line) for line in lines]
                assert trades[0]["pod_id"] == "alpha"
                assert trades[1]["symbol"] == "MSFT"
                assert trades[4]["pod_id"] == "epsilon"

    def test_session_summary_with_realistic_trading(self):
        """Test that session summary reflects realistic trading activity."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = SessionLogger(session_dir=tmpdir)

            # Simulate a realistic trading session with 10 trades
            total_notional = 0.0
            for i in range(10):
                qty = 50.0 + i * 5  # Varying order sizes
                price = 100.0 + i * 2  # Varying prices
                notional = qty * price
                total_notional += notional

                logger.log_trade(
                    pod_id=f"pod_{i % 5}",
                    order_info={
                        "order_id": f"order_{i:03d}",
                        "symbol": ["AAPL", "MSFT", "GOOGL", "TSLA", "NVDA"][i % 5],
                        "side": "BUY" if i % 2 == 0 else "SELL",
                        "qty": qty,
                        "fill_price": price,
                        "notional": notional,
                        "status": "FILLED",
                    },
                )

            logger.close()

            # Check markdown summary
            markdown_file = os.path.join(tmpdir, "session.md")
            with open(markdown_file, "r") as f:
                content = f.read()

            assert "Session Summary" in content
            assert "Total trades executed:" in content
            assert "10" in content
            # Verify notional is calculated (approximate due to rounding)
            assert "Total notional volume:" in content

    def test_trades_for_mandate_and_risk_approval_tracking(self):
        """Test that mandate and risk approval flags are logged with trades."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = SessionLogger(session_dir=tmpdir)

            logger.log_trade(
                pod_id="alpha",
                order_info={
                    "order_id": "mandate_tracked_order",
                    "symbol": "AAPL",
                    "side": "BUY",
                    "qty": 100.0,
                    "fill_price": 150.0,
                    "notional": 15000.0,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "mandate_applied": True,
                    "risk_approved": True,
                    "status": "FILLED",
                },
            )

            logger.close()

            # Verify mandate and risk flags are in the log
            trades_file = os.path.join(tmpdir, "trades.jsonl")
            with open(trades_file, "r") as f:
                trade = json.loads(f.readline())

            assert trade.get("mandate_applied") == True
            assert trade.get("risk_approved") == True

    def test_partial_fills_logged(self):
        """Test that partial fills are properly logged."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = SessionLogger(session_dir=tmpdir)

            # Log initial order (partial fill)
            logger.log_trade(
                pod_id="beta",
                order_info={
                    "order_id": "partial_order_1",
                    "symbol": "MSFT",
                    "side": "BUY",
                    "qty": 50.0,  # Only 50 of 100 filled
                    "fill_price": 300.0,
                    "notional": 15000.0,
                    "status": "PARTIAL",
                },
            )

            # Log completion
            logger.log_trade(
                pod_id="beta",
                order_info={
                    "order_id": "partial_order_2",
                    "symbol": "MSFT",
                    "side": "BUY",
                    "qty": 50.0,  # Remaining 50
                    "fill_price": 301.0,
                    "notional": 15050.0,
                    "status": "FILLED",
                },
            )

            logger.close()

            # Verify both fills logged
            trades_file = os.path.join(tmpdir, "trades.jsonl")
            with open(trades_file, "r") as f:
                lines = f.readlines()
                assert len(lines) == 2

                trade1 = json.loads(lines[0])
                trade2 = json.loads(lines[1])

                assert trade1["status"] == "PARTIAL"
                assert trade2["status"] == "FILLED"
                # Total shares filled = 50 + 50 = 100
                assert trade1["qty"] + trade2["qty"] == 100.0

    def test_high_volume_session(self):
        """Test logging a high-volume trading session (50+ trades)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = SessionLogger(session_dir=tmpdir)

            # Simulate 50 trades
            for i in range(50):
                logger.log_trade(
                    pod_id=f"pod_{i % 5}",
                    order_info={
                        "order_id": f"order_{i:04d}",
                        "symbol": ["AAPL", "MSFT", "GOOGL", "TSLA", "NVDA"][i % 5],
                        "side": "BUY" if i % 3 == 0 else "SELL",
                        "qty": 10.0 + i * 0.5,
                        "fill_price": 100.0 + (i % 10),
                        "notional": (10.0 + i * 0.5) * (100.0 + (i % 10)),
                        "status": "FILLED",
                    },
                )

            logger.close()

            # Verify all trades logged
            trades_file = os.path.join(tmpdir, "trades.jsonl")
            with open(trades_file, "r") as f:
                lines = f.readlines()
                assert len(lines) == 50

            # Verify summary
            markdown_file = os.path.join(tmpdir, "session.md")
            with open(markdown_file, "r") as f:
                content = f.read()

            assert "Session Summary" in content
            assert "Total trades executed:" in content
            assert "50" in content
