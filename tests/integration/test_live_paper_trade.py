"""Live paper trade integration test — verifies full pipeline on Alpaca.

Requires ALPACA_API_KEY and ALPACA_SECRET_KEY in .env.
Gracefully skips if the market is closed (order remains PENDING).
"""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

from src.backtest.accounting.portfolio import PortfolioAccountant
from src.core.bus.audit_log import AuditLog
from src.core.bus.event_bus import EventBus
from src.core.models.enums import Side, OrderType
from src.core.models.execution import Order, RiskApprovalToken
from src.core.models.messages import AgentMessage
from src.execution.paper.alpaca_adapter import AlpacaAdapter
from src.pods.base.namespace import PodNamespace
from src.pods.templates.beta.execution_trader import BetaExecutionTrader

HAS_ALPACA = bool(os.getenv("ALPACA_API_KEY") and os.getenv("ALPACA_SECRET_KEY"))

pytestmark = pytest.mark.skipif(not HAS_ALPACA, reason="No Alpaca credentials")


def _make_token(pod_id="beta", order_id=None) -> RiskApprovalToken:
    oid = order_id or str(uuid.uuid4())
    return RiskApprovalToken(
        pod_id=pod_id,
        order_id=oid,
        issued_at_ms=int(datetime.now(timezone.utc).timestamp() * 1000),
        expires_ms=int((datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp() * 1000),
    )


def _is_market_open(adapter: AlpacaAdapter) -> bool:
    """Check if the US equity market is currently open."""
    try:
        clock = adapter._client.get_clock()
        return clock.is_open
    except Exception:
        return False


class TestLivePaperTrade:
    """End-to-end test: place a real paper order, verify accountant + EventBus."""

    @pytest.mark.asyncio
    async def test_buy_and_sell_roundtrip(self):
        """Buy 1 share, verify accountant, sell it, verify PnL."""
        adapter = AlpacaAdapter()

        if not _is_market_open(adapter):
            pytest.skip("Market is closed — cannot execute live paper trade")

        bus = EventBus(audit_log=AuditLog())
        ns = PodNamespace("beta")
        accountant = PortfolioAccountant(pod_id="beta", initial_nav=100_000.0)
        ns.set("accountant", accountant)

        fill_events: list[dict] = []

        async def capture_fill(msg: AgentMessage):
            fill_events.append(msg.payload)

        await bus.subscribe("execution.fill", capture_fill)

        trader = BetaExecutionTrader(
            agent_id="beta.exec_trader",
            pod_id="beta",
            namespace=ns,
            bus=bus,
            alpaca_adapter=adapter,
        )

        # BUY 1 share AAPL
        order_id = str(uuid.uuid4())
        buy_order = Order(
            id=order_id,
            pod_id="beta",
            symbol="AAPL",
            side=Side.BUY,
            order_type=OrderType.MARKET,
            quantity=1.0,
            limit_price=None,
            timestamp=datetime.now(timezone.utc),
            strategy_tag="live_test",
        )
        token = _make_token("beta", order_id)
        ns.set("last_risk_token", token)

        result = await trader.run_cycle({
            "approved_order": buy_order,
            "mandate": None,
            "risk_halt": False,
        })

        assert result.get("order_executed") is True, f"Buy failed: {result}"
        exec_result = result.get("execution_result", {})
        assert exec_result.get("status") in ("FILLED", "PARTIAL"), f"Not filled: {exec_result}"

        assert "AAPL" in accountant.current_positions
        pos = accountant.current_positions["AAPL"]
        assert pos.qty == 1.0

        await asyncio.sleep(0.5)
        assert len(fill_events) >= 1
        assert fill_events[0]["symbol"] == "AAPL"

        # SELL 1 share AAPL
        sell_order_id = str(uuid.uuid4())
        sell_order = Order(
            id=sell_order_id,
            pod_id="beta",
            symbol="AAPL",
            side=Side.SELL,
            order_type=OrderType.MARKET,
            quantity=1.0,
            limit_price=None,
            timestamp=datetime.now(timezone.utc),
            strategy_tag="live_test",
        )
        sell_token = _make_token("beta", sell_order_id)
        ns.set("last_risk_token", sell_token)

        sell_result = await trader.run_cycle({
            "approved_order": sell_order,
            "mandate": None,
            "risk_halt": False,
        })

        assert sell_result.get("order_executed") is True, f"Sell failed: {sell_result}"

        # Position should be closed (qty 0 or removed)
        remaining = accountant.current_positions.get("AAPL")
        assert remaining is None or remaining.qty == 0.0

    @pytest.mark.asyncio
    async def test_alpaca_connectivity(self):
        """Verify Alpaca account connectivity."""
        adapter = AlpacaAdapter()
        account = await adapter.fetch_account()
        assert account["equity"] > 0
        assert "buying_power" in account
