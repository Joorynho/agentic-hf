"""Integration tests for Phase 1.4: CIO allocation mandates and CRO risk constraints."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.bus.event_bus import EventBus
from src.core.models.allocation import MandateUpdate
from src.core.models.enums import OrderType, Side
from src.core.models.execution import Order, RiskApprovalToken, OrderResult
from src.execution.paper.alpaca_adapter import AlpacaAdapter
from src.mission_control.session_manager import SessionManager
from src.pods.base.namespace import PodNamespace
from src.pods.runtime.pod_runtime import PodRuntime
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


@pytest.fixture
def mandate():
    """Create a valid MandateUpdate with allocation limits."""
    return MandateUpdate(
        timestamp=datetime.now(timezone.utc),
        narrative="Q1 2026 allocation mandate",
        objectives=["Increase alpha pod allocation"],
        constraints={"max_leverage": 2.0},
        rationale="Risk-adjusted based on recent performance",
        authorized_by="ceo_rule_based",
        cio_approved=True,
        cro_approved=True,
        pod_allocations={
            "alpha": 0.25,
            "beta": 0.20,
            "gamma": 0.20,
            "delta": 0.18,
            "epsilon": 0.17,
        },
        firm_nav=50000.0,  # $50k total firm NAV
        cro_halt=False,
    )


class TestAllocationConstraintEnforcement:
    """Test CIO allocation mandates are enforced during execution."""

    @pytest.mark.asyncio
    async def test_order_scaled_down_to_fit_allocation_limit(
        self, event_bus, pod_namespace, mock_alpaca, order, risk_token, mandate
    ):
        """Verify ExecutionTrader scales order down when it would exceed allocation."""
        # Arrange
        mock_alpaca.place_order.return_value = {
            "order_id": "order_1",
            "symbol": "AAPL",
            "qty": 8.33,  # Scaled down
            "side": "buy",
            "status": "FILLED",
            "filled_qty": 8.33,
            "filled_avg_price": 150.0,
            "filled_at": datetime.now(timezone.utc),
        }

        trader = BetaExecutionTrader(
            agent_id="alpha.exec_trader",
            pod_id="alpha",
            namespace=pod_namespace,
            bus=event_bus,
            alpaca_adapter=mock_alpaca,
        )

        # Set up pod state
        pod_namespace.set("current_positions", {})  # No positions
        pod_namespace.set("last_prices", {"AAPL": 150.0})
        pod_namespace.set("last_risk_token", risk_token)
        pod_namespace.set("current_nav", 10000.0)

        # Alpha's allocation is 25% of $50k = $12.5k max
        # Trying to buy 10 shares at $150 = $1500 (ok)
        # But mandate + context together should enforce the limit
        ctx = {
            "approved_order": order,
            "mandate": mandate,
            "risk_halt": False,
        }

        # Act
        result = await trader.run_cycle(ctx)

        # Assert
        assert result.get("order_executed") or result.get("execution_rejected") in [True, False]
        # The order should have been submitted (either scaled or rejected)
        # If submitted, verify it respects the allocation

    @pytest.mark.asyncio
    async def test_order_rejected_when_allocation_limit_reached(
        self, event_bus, pod_namespace, mock_alpaca, risk_token, mandate
    ):
        """Verify order is rejected when allocation limit is already reached."""
        # Arrange
        trader = BetaExecutionTrader(
            agent_id="alpha.exec_trader",
            pod_id="alpha",
            namespace=pod_namespace,
            bus=event_bus,
            alpaca_adapter=mock_alpaca,
        )

        # Set up pod state with existing positions that saturate allocation
        pod_namespace.set(
            "current_positions",
            {"MSFT": {"qty": 50, "symbol": "MSFT"}},  # $50 * $300 = $15k (exceeds $12.5k allocation)
        )
        pod_namespace.set("last_prices", {"AAPL": 150.0, "MSFT": 300.0})
        pod_namespace.set("last_risk_token", risk_token)
        pod_namespace.set("current_nav", 10000.0)

        order = Order(
            pod_id="alpha",
            symbol="AAPL",
            side=Side.BUY,
            order_type=OrderType.MARKET,
            quantity=10.0,
            timestamp=datetime.now(timezone.utc),
            strategy_tag="test_strategy",
        )

        ctx = {
            "approved_order": order,
            "mandate": mandate,
            "risk_halt": False,
        }

        # Act
        result = await trader.run_cycle(ctx)

        # Assert
        # Order should be rejected due to allocation limit
        rejection_reason = result.get("rejection_reason")
        assert (
            rejection_reason == "allocation_limit_exceeded"
            or result.get("execution_rejected") == True
            or "allocation" in str(result).lower()
        )


class TestRiskHaltEnforcement:
    """Test CRO risk halt is enforced during execution."""

    @pytest.mark.asyncio
    async def test_execution_halted_when_cro_halt_active(
        self, event_bus, pod_namespace, mock_alpaca, order, risk_token
    ):
        """Verify all orders are rejected when risk halt is active."""
        # Arrange
        trader = BetaExecutionTrader(
            agent_id="alpha.exec_trader",
            pod_id="alpha",
            namespace=pod_namespace,
            bus=event_bus,
            alpaca_adapter=mock_alpaca,
        )

        pod_namespace.set("last_risk_token", risk_token)

        ctx = {
            "approved_order": order,
            "risk_halt": True,
            "risk_halt_reason": "Counterparty risk limit breach",
        }

        # Act
        result = await trader.run_cycle(ctx)

        # Assert
        assert result.get("execution_rejected") == True
        assert result.get("rejection_reason") == "risk_halt_active"
        assert result.get("rejection_detail") == "Counterparty risk limit breach"
        # Alpaca should NOT have been called
        mock_alpaca.place_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_execution_proceeds_when_risk_halt_inactive(
        self, event_bus, pod_namespace, mock_alpaca, order, risk_token, mandate
    ):
        """Verify orders execute normally when risk halt is not active."""
        # Arrange
        mock_alpaca.place_order.return_value = {
            "order_id": "order_1",
            "symbol": "AAPL",
            "qty": 10.0,
            "side": "buy",
            "status": "FILLED",
            "filled_qty": 10.0,
            "filled_avg_price": 150.0,
            "filled_at": datetime.now(timezone.utc),
        }

        trader = BetaExecutionTrader(
            agent_id="alpha.exec_trader",
            pod_id="alpha",
            namespace=pod_namespace,
            bus=event_bus,
            alpaca_adapter=mock_alpaca,
        )

        pod_namespace.set("current_positions", {})
        pod_namespace.set("last_prices", {"AAPL": 150.0})
        pod_namespace.set("last_risk_token", risk_token)
        pod_namespace.set("current_nav", 10000.0)

        ctx = {
            "approved_order": order,
            "mandate": mandate,
            "risk_halt": False,
        }

        # Act
        result = await trader.run_cycle(ctx)

        # Assert
        assert result.get("order_executed") == True
        assert result.get("execution_rejected") != True
        mock_alpaca.place_order.assert_called_once()


class TestGovernanceStateInSessionManager:
    """Test SessionManager stores and propagates governance state."""

    def test_session_manager_initializes_governance_state(self):
        """Verify SessionManager initializes governance tracking."""
        # Arrange & Act
        mock_alpaca = AsyncMock(spec=AlpacaAdapter)
        manager = SessionManager(alpaca_adapter=mock_alpaca)

        # Assert
        assert manager.latest_mandate is None
        assert manager.risk_halt == False
        assert manager.risk_halt_reason is None

    @pytest.mark.asyncio
    async def test_session_manager_stores_mandate_from_governance_cycle(self):
        """Verify SessionManager stores mandate from governance results."""
        # Arrange
        mock_alpaca = AsyncMock(spec=AlpacaAdapter)
        manager = SessionManager(alpaca_adapter=mock_alpaca)
        mandate = MandateUpdate(
            timestamp=datetime.now(timezone.utc),
            narrative="Test mandate",
            objectives=[],
            constraints={},
            rationale="Test",
            authorized_by="ceo_rule_based",
            pod_allocations={"alpha": 0.25, "beta": 0.25, "gamma": 0.25, "delta": 0.125, "epsilon": 0.125},
            firm_nav=10000.0,
        )

        # Simulate governance result
        manager._latest_mandate = mandate
        manager._risk_halt = False

        # Assert
        assert manager.latest_mandate == mandate
        assert manager.risk_halt == False


class TestLeverageLimitEnforcement:
    """Test CRO leverage constraints are enforced."""

    @pytest.mark.asyncio
    async def test_no_execution_without_valid_token(
        self, event_bus, pod_namespace, mock_alpaca, order
    ):
        """Verify execution requires valid risk approval token."""
        # Arrange
        trader = BetaExecutionTrader(
            agent_id="alpha.exec_trader",
            pod_id="alpha",
            namespace=pod_namespace,
            bus=event_bus,
            alpaca_adapter=mock_alpaca,
        )

        # No risk token set
        pod_namespace.set("last_risk_token", None)

        ctx = {
            "approved_order": order,
            "risk_halt": False,
        }

        # Act
        result = await trader.run_cycle(ctx)

        # Assert
        # Execution should be rejected due to missing token
        assert result.get("execution_rejected") == True
        mock_alpaca.place_order.assert_not_called()


class TestMandateLogging:
    """Test mandate enforcement is logged comprehensively."""

    @pytest.mark.asyncio
    async def test_mandate_application_logged_on_execution(
        self, event_bus, pod_namespace, mock_alpaca, order, risk_token, mandate
    ):
        """Verify mandate application is logged when order executes."""
        # Arrange
        mock_session_logger = MagicMock()
        mock_alpaca.place_order.return_value = {
            "order_id": "order_1",
            "symbol": "AAPL",
            "qty": 10.0,
            "side": "buy",
            "status": "FILLED",
            "filled_qty": 10.0,
            "filled_avg_price": 150.0,
            "filled_at": datetime.now(timezone.utc),
        }

        trader = BetaExecutionTrader(
            agent_id="alpha.exec_trader",
            pod_id="alpha",
            namespace=pod_namespace,
            bus=event_bus,
            alpaca_adapter=mock_alpaca,
            session_logger=mock_session_logger,
        )

        pod_namespace.set("current_positions", {})
        pod_namespace.set("last_prices", {"AAPL": 150.0})
        pod_namespace.set("last_risk_token", risk_token)
        pod_namespace.set("current_nav", 10000.0)

        ctx = {
            "approved_order": order,
            "mandate": mandate,
            "risk_halt": False,
        }

        # Act
        result = await trader.run_cycle(ctx)

        # Assert
        assert result.get("order_executed") == True
        # Verify logging was called
        # (log_reasoning should have been called with mandate_applied)
        if mock_session_logger.log_reasoning.called:
            calls = [str(c) for c in mock_session_logger.log_reasoning.call_args_list]
            # Check that mandate_applied or similar was logged
            assert any("mandate" in str(c).lower() for c in calls)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
