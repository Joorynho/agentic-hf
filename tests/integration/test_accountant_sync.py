"""Tests for MVP4 accountant sync — fills and mark-to-market."""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.backtest.accounting.portfolio import PortfolioAccountant
from src.core.bus.event_bus import EventBus
from src.core.bus.audit_log import AuditLog
from src.core.models.enums import Side, OrderType
from src.core.models.execution import Order, RiskApprovalToken
from src.pods.base.namespace import PodNamespace
from src.pods.templates.beta.execution_trader import BetaExecutionTrader


_TEST_ORDER_ID = str(uuid.uuid4())


def _make_order(symbol="AAPL", side=Side.BUY, qty=10.0) -> Order:
    return Order(
        id=_TEST_ORDER_ID,
        pod_id="beta",
        symbol=symbol,
        side=side,
        order_type=OrderType.MARKET,
        quantity=qty,
        limit_price=None,
        timestamp=datetime.now(timezone.utc),
        strategy_tag="test",
    )


def _make_token(pod_id="beta") -> RiskApprovalToken:
    return RiskApprovalToken(
        pod_id=pod_id,
        order_id=_TEST_ORDER_ID,
        issued_at_ms=int(datetime.now(timezone.utc).timestamp() * 1000),
        expires_ms=int((datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp() * 1000),
    )


def _mock_alpaca_fill(symbol="AAPL", qty=10.0, price=150.0):
    """Return a dict mimicking AlpacaAdapter.place_order() FILLED response."""
    return {
        "order_id": "alpaca-ord-123",
        "symbol": symbol,
        "qty": qty,
        "side": "buy",
        "status": "FILLED",
        "filled_qty": qty,
        "filled_avg_price": price,
        "filled_at": datetime.now(timezone.utc),
    }


class TestAccountantRecordFill:
    """Execution traders must sync fills with PortfolioAccountant."""

    @pytest.fixture
    def setup(self):
        ns = PodNamespace("beta")
        accountant = PortfolioAccountant(pod_id="beta", initial_nav=100_000.0)
        ns.set("accountant", accountant)

        bus = EventBus(audit_log=AuditLog())
        mock_alpaca = AsyncMock()
        trader = BetaExecutionTrader(
            agent_id="beta.exec_trader",
            pod_id="beta",
            namespace=ns,
            bus=bus,
            alpaca_adapter=mock_alpaca,
            session_logger=MagicMock(),
        )
        return ns, accountant, bus, mock_alpaca, trader

    @pytest.mark.asyncio
    async def test_buy_fill_updates_accountant(self, setup):
        ns, accountant, bus, mock_alpaca, trader = setup

        mock_alpaca.place_order = AsyncMock(return_value=_mock_alpaca_fill("AAPL", 10.0, 150.0))
        ns.set("last_risk_token", _make_token())

        order = _make_order("AAPL", Side.BUY, 10.0)
        result = await trader.run_cycle({
            "approved_order": order,
            "mandate": None,
            "risk_halt": False,
        })

        assert result.get("order_executed") is True
        assert "AAPL" in accountant.current_positions
        pos = accountant.current_positions["AAPL"]
        assert pos.qty == 10.0
        assert pos.cost_basis == 150.0

    @pytest.mark.asyncio
    async def test_sell_fill_reduces_position(self, setup):
        ns, accountant, bus, mock_alpaca, trader = setup

        accountant.record_fill_direct("seed", "AAPL", 20.0, 140.0)

        sell_fill = _mock_alpaca_fill("AAPL", 10.0, 155.0)
        sell_fill["side"] = "sell"
        mock_alpaca.place_order = AsyncMock(return_value=sell_fill)
        ns.set("last_risk_token", _make_token())

        order = _make_order("AAPL", Side.SELL, 10.0)
        result = await trader.run_cycle({
            "approved_order": order,
            "mandate": None,
            "risk_halt": False,
        })

        assert result.get("order_executed") is True
        pos = accountant.current_positions["AAPL"]
        assert pos.qty == 10.0
        assert accountant.realized_pnl > 0  # sold at 155, cost was 140

    @pytest.mark.asyncio
    async def test_rejected_order_does_not_update_accountant(self, setup):
        ns, accountant, bus, mock_alpaca, trader = setup

        rejected = {
            "order_id": None, "symbol": "AAPL", "qty": 10, "side": "buy",
            "status": "REJECTED", "filled_qty": 0.0,
            "filled_avg_price": None, "filled_at": None,
        }
        mock_alpaca.place_order = AsyncMock(return_value=rejected)
        ns.set("last_risk_token", _make_token())

        order = _make_order("AAPL", Side.BUY, 10.0)
        await trader.run_cycle({
            "approved_order": order,
            "mandate": None,
            "risk_halt": False,
        })

        assert len(accountant.current_positions) == 0
        assert accountant.nav == 100_000.0

    @pytest.mark.asyncio
    async def test_nav_reflects_fill(self, setup):
        ns, accountant, bus, mock_alpaca, trader = setup
        initial_nav = accountant.nav

        mock_alpaca.place_order = AsyncMock(return_value=_mock_alpaca_fill("MSFT", 5.0, 400.0))
        ns.set("last_risk_token", _make_token())

        order = _make_order("MSFT", Side.BUY, 5.0)
        await trader.run_cycle({
            "approved_order": order,
            "mandate": None,
            "risk_halt": False,
        })

        assert "MSFT" in accountant.current_positions
        assert accountant.nav == initial_nav  # NAV stays same until mark-to-market moves price


class TestMarkToMarket:
    """Session manager must call mark_to_market after bar pushes."""

    def test_mark_to_market_updates_unrealized_pnl(self):
        accountant = PortfolioAccountant(pod_id="beta", initial_nav=100_000.0)
        accountant.record_fill_direct("ord-1", "AAPL", 10.0, 150.0)

        new_nav = accountant.mark_to_market({"AAPL": 160.0})

        pos = accountant.current_positions["AAPL"]
        assert pos.current_price == 160.0
        assert pos.unrealized_pnl == 100.0  # 10 shares * $10 gain
        assert new_nav > 100_000.0

    def test_mark_to_market_tracks_hwm(self):
        accountant = PortfolioAccountant(pod_id="beta", initial_nav=100_000.0)
        accountant.record_fill_direct("ord-1", "AAPL", 10.0, 150.0)

        accountant.mark_to_market({"AAPL": 200.0})
        accountant.mark_to_market({"AAPL": 180.0})

        assert accountant.drawdown_from_hwm() < 0  # below HWM
