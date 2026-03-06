"""Integration tests for MVP4 execution pipeline — ExecutionTrader → Alpaca orders."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, MagicMock
from uuid import uuid4

import pytest

from src.core.bus.event_bus import EventBus
from src.core.models.enums import OrderType, Side
from src.core.models.execution import Order, RiskApprovalToken, OrderResult
from src.execution.paper.alpaca_adapter import AlpacaAdapter
from src.pods.base.namespace import PodNamespace
from src.pods.templates.beta.execution_trader import BetaExecutionTrader
from src.pods.templates.gamma.execution_trader import GammaExecutionTrader

logger = logging.getLogger(__name__)


@pytest.fixture
def event_bus():
    """Create an EventBus for testing."""
    return EventBus()


@pytest.fixture
def pod_namespace():
    """Create a PodNamespace for testing."""
    return PodNamespace(pod_id="alpha")


@pytest.fixture
def mock_alpaca():
    """Create a mock AlpacaAdapter."""
    mock = AsyncMock(spec=AlpacaAdapter)
    return mock


@pytest.fixture
def order():
    """Create a test Order."""
    return Order(
        pod_id="alpha",
        symbol="AAPL",
        side=Side.BUY,
        order_type=OrderType.MARKET,
        quantity=10.0,
        limit_price=None,
        timestamp=datetime.now(timezone.utc),
        strategy_tag="test_strategy",
    )


@pytest.fixture
def risk_token():
    """Create a valid RiskApprovalToken."""
    return RiskApprovalToken(
        pod_id="alpha",
        order_id=uuid4(),
    )


@pytest.mark.asyncio
async def test_execution_trader_submits_order_to_alpaca(
    event_bus, pod_namespace, mock_alpaca, order, risk_token
):
    """Verify ExecutionTrader calls alpaca.place_order() and returns OrderResult."""
    # Arrange
    mock_alpaca.place_order.return_value = {
        "order_id": "order_123",
        "symbol": "AAPL",
        "qty": 10.0,
        "side": "buy",
        "status": "FILLED",
        "filled_qty": 10.0,
        "filled_avg_price": 150.5,
        "filled_at": datetime.now(timezone.utc),
    }

    trader = BetaExecutionTrader(
        agent_id="alpha.exec_trader",
        pod_id="alpha",
        namespace=pod_namespace,
        bus=event_bus,
        alpaca_adapter=mock_alpaca,
    )
    trader.store("last_risk_token", risk_token)

    # Act
    context = {"approved_order": order}
    result = await trader.run_cycle(context)

    # Assert
    assert result["order_executed"] is True
    assert "execution_result" in result
    execution_result = result["execution_result"]
    assert execution_result["order_id"] == "order_123"
    assert execution_result["status"] == "FILLED"
    assert execution_result["fill_price"] == 150.5
    assert execution_result["fill_qty"] == 10.0

    # Verify Alpaca was called with correct parameters
    mock_alpaca.place_order.assert_called_once_with(
        symbol="AAPL",
        qty=10.0,
        side="buy",
        order_type="market",
        limit_price=None,
    )


@pytest.mark.asyncio
async def test_execution_trader_handles_partial_fill(
    event_bus, pod_namespace, mock_alpaca, order, risk_token
):
    """Verify ExecutionTrader handles partial fills correctly."""
    # Arrange
    mock_alpaca.place_order.return_value = {
        "order_id": "order_456",
        "symbol": "AAPL",
        "qty": 10.0,
        "side": "buy",
        "status": "PARTIAL",
        "filled_qty": 5.0,
        "filled_avg_price": 150.25,
        "filled_at": datetime.now(timezone.utc),
    }

    trader = GammaExecutionTrader(
        agent_id="gamma.exec_trader",
        pod_id="gamma",
        namespace=PodNamespace("gamma"),
        bus=event_bus,
        alpaca_adapter=mock_alpaca,
    )
    trader.store("last_risk_token", risk_token)

    # Act
    context = {"approved_order": order}
    result = await trader.run_cycle(context)

    # Assert
    assert result["order_executed"] is True
    execution_result = result["execution_result"]
    assert execution_result["status"] == "PARTIAL"
    assert execution_result["fill_qty"] == 5.0


@pytest.mark.asyncio
async def test_execution_trader_handles_pending_order(
    event_bus, pod_namespace, mock_alpaca, order, risk_token
):
    """Verify ExecutionTrader returns PENDING when order doesn't fill."""
    # Arrange
    mock_alpaca.place_order.return_value = {
        "order_id": "order_789",
        "symbol": "AAPL",
        "qty": 10.0,
        "side": "buy",
        "status": "PENDING",
        "filled_qty": 0.0,
        "filled_avg_price": None,
        "filled_at": None,
    }

    trader = BetaExecutionTrader(
        agent_id="alpha.exec_trader",
        pod_id="alpha",
        namespace=pod_namespace,
        bus=event_bus,
        alpaca_adapter=mock_alpaca,
    )
    trader.store("last_risk_token", risk_token)

    # Act
    context = {"approved_order": order}
    result = await trader.run_cycle(context)

    # Assert
    assert result["order_executed"] is True
    execution_result = result["execution_result"]
    assert execution_result["status"] == "PENDING"
    assert execution_result["fill_qty"] == 0.0


@pytest.mark.asyncio
async def test_execution_trader_rejects_invalid_token(
    event_bus, pod_namespace, mock_alpaca, order
):
    """Verify ExecutionTrader rejects order with invalid RiskApprovalToken."""
    # Arrange
    trader = BetaExecutionTrader(
        agent_id="alpha.exec_trader",
        pod_id="alpha",
        namespace=pod_namespace,
        bus=event_bus,
        alpaca_adapter=mock_alpaca,
    )
    # No token stored (or expired token)

    # Act
    context = {"approved_order": order}
    result = await trader.run_cycle(context)

    # Assert
    assert result["execution_rejected"] is True
    mock_alpaca.place_order.assert_not_called()


@pytest.mark.asyncio
async def test_execution_trader_handles_alpaca_error(
    event_bus, pod_namespace, mock_alpaca, order, risk_token
):
    """Verify ExecutionTrader handles Alpaca API failures gracefully."""
    # Arrange
    mock_alpaca.place_order.side_effect = Exception("Alpaca API Error: Connection timeout")

    trader = GammaExecutionTrader(
        agent_id="gamma.exec_trader",
        pod_id="gamma",
        namespace=PodNamespace("gamma"),
        bus=event_bus,
        alpaca_adapter=mock_alpaca,
    )
    trader.store("last_risk_token", risk_token)

    # Act
    context = {"approved_order": order}
    result = await trader.run_cycle(context)

    # Assert
    assert result["order_executed"] is False
    assert "execution_error" in result


@pytest.mark.asyncio
async def test_execution_trader_falls_back_to_paper_adapter(
    event_bus, pod_namespace, order, risk_token
):
    """Verify ExecutionTrader falls back to paper adapter when no Alpaca adapter."""
    # Arrange
    trader = BetaExecutionTrader(
        agent_id="alpha.exec_trader",
        pod_id="alpha",
        namespace=pod_namespace,
        bus=event_bus,
        alpaca_adapter=None,  # No Alpaca adapter
    )
    trader.store("last_risk_token", risk_token)

    # Act
    context = {"approved_order": order}
    result = await trader.run_cycle(context)

    # Assert
    assert result["order_queued"] is True
    # Verify order was queued in namespace
    pending = trader.recall("pending_orders", [])
    assert len(pending) == 1
    assert pending[0]["symbol"] == "AAPL"


@pytest.mark.asyncio
async def test_execution_trader_processes_limit_orders(
    event_bus, pod_namespace, mock_alpaca, risk_token
):
    """Verify ExecutionTrader handles limit orders correctly."""
    # Arrange
    limit_order = Order(
        pod_id="alpha",
        symbol="MSFT",
        side=Side.SELL,
        order_type=OrderType.LIMIT,
        quantity=5.0,
        limit_price=300.0,
        timestamp=datetime.now(timezone.utc),
        strategy_tag="test_strategy",
    )

    mock_alpaca.place_order.return_value = {
        "order_id": "limit_order_999",
        "symbol": "MSFT",
        "qty": 5.0,
        "side": "sell",
        "status": "FILLED",
        "filled_qty": 5.0,
        "filled_avg_price": 300.0,
        "filled_at": datetime.now(timezone.utc),
    }

    trader = GammaExecutionTrader(
        agent_id="gamma.exec_trader",
        pod_id="gamma",
        namespace=PodNamespace("gamma"),
        bus=event_bus,
        alpaca_adapter=mock_alpaca,
    )
    trader.store("last_risk_token", risk_token)

    # Act
    context = {"approved_order": limit_order}
    result = await trader.run_cycle(context)

    # Assert
    assert result["order_executed"] is True
    execution_result = result["execution_result"]
    assert execution_result["symbol"] == "MSFT"
    assert execution_result["side"] == "sell"

    # Verify Alpaca was called with limit order parameters
    mock_alpaca.place_order.assert_called_once_with(
        symbol="MSFT",
        qty=5.0,
        side="sell",
        order_type="limit",
        limit_price=300.0,
    )


@pytest.mark.asyncio
async def test_execution_trader_no_order_in_context(
    event_bus, pod_namespace, mock_alpaca, risk_token
):
    """Verify ExecutionTrader handles missing order gracefully."""
    # Arrange
    trader = BetaExecutionTrader(
        agent_id="alpha.exec_trader",
        pod_id="alpha",
        namespace=pod_namespace,
        bus=event_bus,
        alpaca_adapter=mock_alpaca,
    )

    # Act
    context = {}  # No approved_order
    result = await trader.run_cycle(context)

    # Assert
    assert result == {}
    mock_alpaca.place_order.assert_not_called()


@pytest.mark.asyncio
async def test_order_result_model_serialization(event_bus, pod_namespace, mock_alpaca, risk_token):
    """Verify OrderResult model can be serialized to JSON."""
    # Arrange
    googl_order = Order(
        pod_id="gamma",
        symbol="GOOGL",
        side=Side.BUY,
        order_type=OrderType.MARKET,
        quantity=2.0,
        limit_price=None,
        timestamp=datetime.now(timezone.utc),
        strategy_tag="test_strategy",
    )

    mock_alpaca.place_order.return_value = {
        "order_id": "order_ser_test",
        "symbol": "GOOGL",
        "qty": 2.0,
        "side": "buy",
        "status": "FILLED",
        "filled_qty": 2.0,
        "filled_avg_price": 140.5,
        "filled_at": datetime.now(timezone.utc),
    }

    trader = GammaExecutionTrader(
        agent_id="gamma.exec_trader",
        pod_id="gamma",
        namespace=PodNamespace("gamma"),
        bus=event_bus,
        alpaca_adapter=mock_alpaca,
    )
    trader.store("last_risk_token", risk_token)

    # Act
    context = {"approved_order": googl_order}
    result = await trader.run_cycle(context)

    # Assert - Verify serialization works
    execution_result = result["execution_result"]
    assert isinstance(execution_result, dict)
    assert execution_result["order_id"] == "order_ser_test"
    assert execution_result["symbol"] == "GOOGL"
    assert execution_result["status"] == "FILLED"
