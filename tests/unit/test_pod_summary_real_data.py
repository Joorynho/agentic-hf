"""Unit tests for PodSummary with real trading data.

Tests verify that PodSummary correctly includes:
- Real open positions from PortfolioAccountant
- NAV from portfolio accountant (initial capital + realized PnL + unrealized PnL)
- Leverage calculated from total notional / NAV
- Risk metrics with correct values
"""
from __future__ import annotations

import asyncio
import pytest
from datetime import datetime

from src.backtest.accounting.portfolio import PortfolioAccountant
from src.core.models.enums import PodStatus
from src.core.models.pod_summary import PodSummary, PodRiskMetrics, PodExposureBucket
from src.core.models.execution import PodPosition
from src.pods.base.namespace import PodNamespace
from src.pods.runtime.pod_runtime import PodRuntime
from src.core.bus.event_bus import EventBus


class TestPodSummaryRealPositions:
    """Test that PodSummary includes actual open positions from PortfolioAccountant."""

    @pytest.mark.asyncio
    async def test_pod_summary_includes_real_positions(self):
        """Verify PodSummary includes actual open positions."""
        # Setup
        pod_id = "test_pod_alpha"
        initial_capital = 10000.0

        # Create namespace with PortfolioAccountant
        namespace = PodNamespace(pod_id)
        accountant = PortfolioAccountant(pod_id=pod_id, initial_nav=initial_capital)
        namespace.set("accountant", accountant)

        # Record a fill: 10 shares of AAPL @ $150
        accountant.record_fill_direct(
            order_id="order_1",
            symbol="AAPL",
            qty=10.0,
            fill_price=150.0,
        )

        # Update market price
        accountant.mark_to_market({"AAPL": 155.0})

        # Create runtime and get summary
        gateway = None  # Gateway not needed for summary generation
        bus = EventBus()
        runtime = PodRuntime(pod_id=pod_id, namespace=namespace, gateway=gateway, bus=bus)

        summary = await runtime.get_summary()

        # Assertions
        assert len(summary.positions) == 1
        position = summary.positions[0]
        assert position.symbol == "AAPL"
        assert position.qty == 10.0
        assert position.current_price == 155.0
        assert position.unrealized_pnl == pytest.approx(50.0)  # 10 * (155 - 150)
        assert position.notional == pytest.approx(1550.0)  # 10 * 155

    @pytest.mark.asyncio
    async def test_pod_summary_multiple_positions(self):
        """Verify PodSummary correctly handles multiple open positions."""
        # Setup
        pod_id = "test_pod_beta"
        initial_capital = 50000.0

        namespace = PodNamespace(pod_id)
        accountant = PortfolioAccountant(pod_id=pod_id, initial_nav=initial_capital)
        namespace.set("accountant", accountant)

        # Record fills for 3 stocks
        accountant.record_fill_direct("order_1", "AAPL", qty=100.0, fill_price=150.0)
        accountant.record_fill_direct("order_2", "MSFT", qty=50.0, fill_price=400.0)
        accountant.record_fill_direct("order_3", "GOOGL", qty=10.0, fill_price=2500.0)

        # Update prices
        accountant.mark_to_market({
            "AAPL": 155.0,
            "MSFT": 410.0,
            "GOOGL": 2550.0,
        })

        # Get summary
        bus = EventBus()
        runtime = PodRuntime(pod_id=pod_id, namespace=namespace, gateway=None, bus=bus)
        summary = await runtime.get_summary()

        # Assertions
        assert len(summary.positions) == 3

        # Verify each position
        positions_by_symbol = {p.symbol: p for p in summary.positions}

        assert positions_by_symbol["AAPL"].qty == 100.0
        assert positions_by_symbol["AAPL"].unrealized_pnl == pytest.approx(500.0)

        assert positions_by_symbol["MSFT"].qty == 50.0
        assert positions_by_symbol["MSFT"].unrealized_pnl == pytest.approx(500.0)

        assert positions_by_symbol["GOOGL"].qty == 10.0
        assert positions_by_symbol["GOOGL"].unrealized_pnl == pytest.approx(500.0)


class TestPodSummaryNAV:
    """Test that PodSummary.nav correctly reflects portfolio accountant NAV."""

    @pytest.mark.asyncio
    async def test_pod_summary_nav_reflects_unrealized_pnl(self):
        """Verify PodSummary.nav = initial_capital + unrealized_pnl + realized_pnl."""
        # Setup
        pod_id = "test_pod_gamma"
        initial_capital = 100000.0

        namespace = PodNamespace(pod_id)
        accountant = PortfolioAccountant(pod_id=pod_id, initial_nav=initial_capital)
        namespace.set("accountant", accountant)

        # Record a buy: 100 AAPL @ $100 = $10,000
        accountant.record_fill_direct("order_1", "AAPL", qty=100.0, fill_price=100.0)

        # Price goes up to $110, so unrealized PnL = 100 * (110 - 100) = $1,000
        accountant.mark_to_market({"AAPL": 110.0})

        # Get summary
        bus = EventBus()
        runtime = PodRuntime(pod_id=pod_id, namespace=namespace, gateway=None, bus=bus)
        summary = await runtime.get_summary()

        # Expected NAV = initial ($100k) + unrealized ($1k) = $101k
        expected_nav = initial_capital + 1000.0

        assert summary.risk_metrics.nav == pytest.approx(expected_nav)
        assert summary.nav == pytest.approx(expected_nav)
        assert summary.risk_metrics.daily_pnl == pytest.approx(1000.0)

    @pytest.mark.asyncio
    async def test_pod_summary_nav_after_realized_pnl(self):
        """Verify NAV includes both realized and unrealized PnL."""
        # Setup
        pod_id = "test_pod_delta"
        initial_capital = 50000.0

        namespace = PodNamespace(pod_id)
        accountant = PortfolioAccountant(pod_id=pod_id, initial_nav=initial_capital)
        namespace.set("accountant", accountant)

        # Buy 100 shares @ $100
        accountant.record_fill_direct("order_1", "AAPL", qty=100.0, fill_price=100.0)
        # Sell 100 shares @ $110 (realizes +$1,000 profit)
        accountant.record_fill_direct("order_2", "AAPL", qty=-100.0, fill_price=110.0)

        # Now buy 50 shares @ $115 (cost = $5,750)
        accountant.record_fill_direct("order_3", "AAPL", qty=50.0, fill_price=115.0)

        # Price falls to $110, unrealized = 50 * (110 - 115) = -$250
        accountant.mark_to_market({"AAPL": 110.0})

        # Get summary
        bus = EventBus()
        runtime = PodRuntime(pod_id=pod_id, namespace=namespace, gateway=None, bus=bus)
        summary = await runtime.get_summary()

        # Expected NAV = initial ($50k) + realized ($1k) + unrealized (-$250) = $50,750
        expected_nav = initial_capital + 1000.0 - 250.0

        assert summary.risk_metrics.nav == pytest.approx(expected_nav, abs=1.0)
        assert summary.risk_metrics.daily_pnl == pytest.approx(750.0, abs=1.0)


class TestPodSummaryLeverage:
    """Test that gross leverage is correctly calculated from positions."""

    @pytest.mark.asyncio
    async def test_pod_summary_leverage_single_position(self):
        """Verify gross_leverage = total_notional / nav."""
        # Setup: 100 AAPL @ $150 = $15k notional, NAV $10k, so leverage = 1.5x
        pod_id = "test_pod_epsilon"
        initial_capital = 10000.0

        namespace = PodNamespace(pod_id)
        accountant = PortfolioAccountant(pod_id=pod_id, initial_nav=initial_capital)
        namespace.set("accountant", accountant)

        accountant.record_fill_direct("order_1", "AAPL", qty=100.0, fill_price=150.0)
        accountant.mark_to_market({"AAPL": 150.0})

        # Get summary
        bus = EventBus()
        runtime = PodRuntime(pod_id=pod_id, namespace=namespace, gateway=None, bus=bus)

        summary = await runtime.get_summary()

        # Total notional = 100 * 150 = $15,000
        # NAV = initial $10k
        # Leverage = 15,000 / 10,000 = 1.5x
        assert summary.risk_metrics.gross_leverage == pytest.approx(1.5)

    @pytest.mark.asyncio
    async def test_pod_summary_leverage_multiple_positions(self):
        """Verify gross leverage sums all position notionals."""
        pod_id = "test_pod_zeta"
        initial_capital = 100000.0

        namespace = PodNamespace(pod_id)
        accountant = PortfolioAccountant(pod_id=pod_id, initial_nav=initial_capital)
        namespace.set("accountant", accountant)

        # Buy 100 shares of AAPL @ $100
        accountant.record_fill_direct("order_1", "AAPL", qty=100.0, fill_price=100.0)
        # Buy 50 shares of MSFT @ $200
        accountant.record_fill_direct("order_2", "MSFT", qty=50.0, fill_price=200.0)

        accountant.mark_to_market({"AAPL": 100.0, "MSFT": 200.0})

        # Total notional = (100 * 100) + (50 * 200) = 10k + 10k = 20k
        # Leverage = 20k / 100k = 0.2x

        bus = EventBus()
        runtime = PodRuntime(pod_id=pod_id, namespace=namespace, gateway=None, bus=bus)
        summary = await runtime.get_summary()

        assert summary.risk_metrics.gross_leverage == pytest.approx(0.2)

    @pytest.mark.asyncio
    async def test_pod_summary_leverage_with_shorts(self):
        """Verify gross leverage includes absolute values of short positions."""
        pod_id = "test_pod_eta"
        initial_capital = 100000.0

        namespace = PodNamespace(pod_id)
        accountant = PortfolioAccountant(pod_id=pod_id, initial_nav=initial_capital)
        namespace.set("accountant", accountant)

        # Long 100 AAPL @ $100 = $10k
        accountant.record_fill_direct("order_1", "AAPL", qty=100.0, fill_price=100.0)
        # Short 50 MSFT @ $200 = -$10k (but notional is absolute value = $10k)
        accountant.record_fill_direct("order_2", "MSFT", qty=-50.0, fill_price=200.0)

        accountant.mark_to_market({"AAPL": 100.0, "MSFT": 200.0})

        # Total notional = 10k + 10k = 20k
        # Leverage = 20k / 100k = 0.2x

        bus = EventBus()
        runtime = PodRuntime(pod_id=pod_id, namespace=namespace, gateway=None, bus=bus)
        summary = await runtime.get_summary()

        assert summary.risk_metrics.gross_leverage == pytest.approx(0.2)


class TestPodSummaryRiskMetrics:
    """Test that risk metrics are properly populated."""

    @pytest.mark.asyncio
    async def test_pod_summary_risk_metrics_structure(self):
        """Verify all risk metrics fields are populated."""
        pod_id = "test_pod_theta"
        initial_capital = 50000.0

        namespace = PodNamespace(pod_id)
        accountant = PortfolioAccountant(pod_id=pod_id, initial_nav=initial_capital)
        namespace.set("accountant", accountant)

        # Add one position
        accountant.record_fill_direct("order_1", "AAPL", qty=10.0, fill_price=100.0)
        accountant.mark_to_market({"AAPL": 105.0})

        bus = EventBus()
        runtime = PodRuntime(pod_id=pod_id, namespace=namespace, gateway=None, bus=bus)
        summary = await runtime.get_summary()

        # Verify all risk metric fields exist and have values
        metrics = summary.risk_metrics
        assert metrics.pod_id == pod_id
        assert isinstance(metrics.timestamp, datetime)
        assert metrics.nav > 0
        assert isinstance(metrics.daily_pnl, float)
        assert isinstance(metrics.drawdown_from_hwm, float)
        assert isinstance(metrics.current_vol_ann, float)
        assert isinstance(metrics.gross_leverage, float)
        assert isinstance(metrics.net_leverage, float)
        assert isinstance(metrics.var_95_1d, float)
        assert isinstance(metrics.es_95_1d, float)

    @pytest.mark.asyncio
    async def test_pod_summary_status_is_active(self):
        """Verify pod status is ACTIVE when initialized."""
        pod_id = "test_pod_iota"
        initial_capital = 10000.0

        namespace = PodNamespace(pod_id)
        accountant = PortfolioAccountant(pod_id=pod_id, initial_nav=initial_capital)
        namespace.set("accountant", accountant)

        bus = EventBus()
        runtime = PodRuntime(pod_id=pod_id, namespace=namespace, gateway=None, bus=bus)
        summary = await runtime.get_summary()

        assert summary.status == PodStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_pod_summary_empty_positions_when_no_trades(self):
        """Verify positions list is empty when no trades recorded."""
        pod_id = "test_pod_kappa"
        initial_capital = 10000.0

        namespace = PodNamespace(pod_id)
        accountant = PortfolioAccountant(pod_id=pod_id, initial_nav=initial_capital)
        namespace.set("accountant", accountant)

        bus = EventBus()
        runtime = PodRuntime(pod_id=pod_id, namespace=namespace, gateway=None, bus=bus)
        summary = await runtime.get_summary()

        assert len(summary.positions) == 0
        assert summary.risk_metrics.gross_leverage == 0.0


class TestPodSummaryExposureBuckets:
    """Test exposure bucket calculation."""

    @pytest.mark.asyncio
    async def test_pod_summary_exposure_buckets_us_equities(self):
        """Verify exposure buckets correctly classify positions."""
        pod_id = "test_pod_lambda"
        initial_capital = 100000.0

        namespace = PodNamespace(pod_id)
        accountant = PortfolioAccountant(pod_id=pod_id, initial_nav=initial_capital)
        namespace.set("accountant", accountant)

        # 50% allocation to AAPL
        accountant.record_fill_direct("order_1", "AAPL", qty=500.0, fill_price=100.0)
        accountant.mark_to_market({"AAPL": 100.0})

        bus = EventBus()
        runtime = PodRuntime(pod_id=pod_id, namespace=namespace, gateway=None, bus=bus)
        summary = await runtime.get_summary()

        # Should have one bucket for US equities
        assert len(summary.exposure_buckets) == 1
        bucket = summary.exposure_buckets[0]
        assert bucket.asset_class == "US_EQUITIES"
        assert bucket.notional_pct_nav == pytest.approx(0.5)
