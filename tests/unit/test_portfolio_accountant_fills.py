"""Unit tests for PortfolioAccountant fill tracking (Phase 1.2)."""

import pytest
from datetime import datetime, timezone

from src.backtest.accounting.portfolio import PortfolioAccountant


@pytest.fixture
def accountant():
    """Create a fresh PortfolioAccountant instance with $10k starting capital."""
    return PortfolioAccountant(pod_id="test_pod", initial_nav=10000.0)


class TestFillRecording:
    """Tests for recording fills and updating positions."""

    def test_record_fill_direct_buy_single_position(self, accountant):
        """Test recording a BUY fill creates a position."""
        accountant.record_fill_direct("order_1", "AAPL", qty=10.0, fill_price=150.0)

        assert accountant._positions["AAPL"]["quantity"] == 10.0
        assert accountant._cost_basis["AAPL"] == 150.0
        assert len(accountant._fill_log) == 1
        assert accountant._fill_log[0]["order_id"] == "order_1"
        assert accountant._fill_log[0]["symbol"] == "AAPL"
        assert accountant._fill_log[0]["qty"] == 10.0

    def test_record_fill_direct_sell_closes_position(self, accountant):
        """Test SELL fill at correct price closes position."""
        accountant.record_fill_direct("order_1", "AAPL", qty=10.0, fill_price=150.0)
        accountant.record_fill_direct("order_2", "AAPL", qty=-10.0, fill_price=160.0)

        assert accountant._positions["AAPL"]["quantity"] == 0.0
        assert accountant._cost_basis["AAPL"] == 0.0
        # Realized PnL = qty_reduced * (sell_price - cost_basis) = 10 * (160 - 150) = 100
        assert accountant._realized_pnl == 100.0

    def test_record_fill_direct_partial_sell_updates_position(self, accountant):
        """Test partial SELL updates position and realizes PnL on reduced portion."""
        accountant.record_fill_direct("order_1", "AAPL", qty=20.0, fill_price=100.0)
        accountant.record_fill_direct("order_2", "AAPL", qty=-5.0, fill_price=105.0)

        assert accountant._positions["AAPL"]["quantity"] == 15.0
        assert accountant._cost_basis["AAPL"] == 100.0
        # Partial close: 5 * (105 - 100) = 25
        assert accountant._realized_pnl == 25.0

    def test_record_multiple_buys_weighted_average_cost_basis(self, accountant):
        """Test weighted average cost basis with multiple BUY fills."""
        accountant.record_fill_direct("order_1", "AAPL", qty=10.0, fill_price=100.0)
        accountant.record_fill_direct("order_2", "AAPL", qty=20.0, fill_price=110.0)

        # Weighted average = (10*100 + 20*110) / 30 = 3200 / 30 = 106.67
        assert accountant._positions["AAPL"]["quantity"] == 30.0
        assert abs(accountant._cost_basis["AAPL"] - 106.67) < 0.01

    def test_record_fill_direct_multiple_symbols(self, accountant):
        """Test tracking multiple positions across symbols."""
        accountant.record_fill_direct("order_1", "AAPL", qty=10.0, fill_price=150.0)
        accountant.record_fill_direct("order_2", "MSFT", qty=5.0, fill_price=300.0)

        assert accountant._positions["AAPL"]["quantity"] == 10.0
        assert accountant._positions["MSFT"]["quantity"] == 5.0
        assert accountant._cost_basis["AAPL"] == 150.0
        assert accountant._cost_basis["MSFT"] == 300.0

    def test_record_fill_with_explicit_timestamp(self, accountant):
        """Test recording fill with explicit timestamp."""
        ts = datetime(2025, 3, 6, 12, 0, 0, tzinfo=timezone.utc)
        accountant.record_fill_direct(
            "order_1", "AAPL", qty=10.0, fill_price=150.0, filled_at=ts
        )

        assert accountant._fill_log[0]["timestamp"] == ts


class TestPositionTracking:
    """Tests for current_positions property and position snapshots."""

    def test_current_positions_empty_when_no_fills(self, accountant):
        """Test current_positions returns empty dict when no fills recorded."""
        positions = accountant.current_positions
        assert positions == {}

    def test_current_positions_single_long_position(self, accountant):
        """Test current_positions returns single long position."""
        accountant.record_fill_direct("order_1", "AAPL", qty=10.0, fill_price=150.0)
        accountant._update_last_price("AAPL", 155.0)

        positions = accountant.current_positions
        assert len(positions) == 1
        assert "AAPL" in positions

        snap = positions["AAPL"]
        assert snap.symbol == "AAPL"
        assert snap.qty == 10.0
        assert snap.cost_basis == 150.0
        assert snap.current_price == 155.0
        assert snap.unrealized_pnl == 50.0  # 10 * (155 - 150)

    def test_current_positions_excludes_closed_positions(self, accountant):
        """Test that closed positions are excluded from current_positions."""
        accountant.record_fill_direct("order_1", "AAPL", qty=10.0, fill_price=150.0)
        accountant.record_fill_direct("order_2", "AAPL", qty=-10.0, fill_price=160.0)

        positions = accountant.current_positions
        assert "AAPL" not in positions

    def test_current_positions_multiple_symbols(self, accountant):
        """Test current_positions with multiple open positions."""
        accountant.record_fill_direct("order_1", "AAPL", qty=10.0, fill_price=150.0)
        accountant.record_fill_direct("order_2", "MSFT", qty=5.0, fill_price=300.0)
        accountant._update_last_price("AAPL", 155.0)
        accountant._update_last_price("MSFT", 305.0)

        positions = accountant.current_positions
        assert len(positions) == 2
        assert positions["AAPL"].unrealized_pnl == 50.0
        assert positions["MSFT"].unrealized_pnl == 25.0

    def test_position_snapshot_notional_property(self, accountant):
        """Test PositionSnapshot.notional property."""
        accountant.record_fill_direct("order_1", "AAPL", qty=10.0, fill_price=150.0)
        accountant._update_last_price("AAPL", 155.0)

        snap = accountant.current_positions["AAPL"]
        assert snap.notional == 1550.0  # 10 * 155

    def test_position_snapshot_pnl_pct_property(self, accountant):
        """Test PositionSnapshot.pnl_pct property."""
        accountant.record_fill_direct("order_1", "AAPL", qty=100.0, fill_price=100.0)
        accountant._update_last_price("AAPL", 110.0)

        snap = accountant.current_positions["AAPL"]
        assert abs(snap.pnl_pct - 10.0) < 0.01  # (110 - 100) / 100 * 100 = 10%


class TestNAVCalculation:
    """Tests for NAV, daily PnL, and realized PnL properties."""

    def test_nav_with_no_positions(self, accountant):
        """Test NAV equals starting capital when no positions."""
        assert accountant.nav == 10000.0

    def test_nav_with_unrealized_gain(self, accountant):
        """Test NAV reflects unrealized gains."""
        accountant.record_fill_direct("order_1", "AAPL", qty=100.0, fill_price=100.0)
        accountant._update_last_price("AAPL", 105.0)

        # NAV = 10000 + 100*(105-100) = 10500
        assert accountant.nav == 10500.0

    def test_nav_with_unrealized_loss(self, accountant):
        """Test NAV reflects unrealized losses."""
        accountant.record_fill_direct("order_1", "AAPL", qty=100.0, fill_price=100.0)
        accountant._update_last_price("AAPL", 95.0)

        # NAV = 10000 + 100*(95-100) = 9500
        assert accountant.nav == 9500.0

    def test_nav_with_realized_gain(self, accountant):
        """Test NAV reflects realized gains from closed positions."""
        accountant.record_fill_direct("order_1", "AAPL", qty=100.0, fill_price=100.0)
        accountant.record_fill_direct("order_2", "AAPL", qty=-100.0, fill_price=110.0)

        # Realized PnL = 100 * (110 - 100) = 1000
        # NAV = 10000 + 1000 = 11000
        assert accountant.nav == 11000.0
        assert accountant.realized_pnl == 1000.0

    def test_nav_with_mixed_realized_and_unrealized(self, accountant):
        """Test NAV with both realized and unrealized PnL."""
        # Buy AAPL at 100, sell half at 110 (realized gain 500)
        accountant.record_fill_direct("order_1", "AAPL", qty=100.0, fill_price=100.0)
        accountant.record_fill_direct("order_2", "AAPL", qty=-50.0, fill_price=110.0)
        # Now hold 50 @ 100 cost, price moves to 105 (unrealized gain 250)
        accountant._update_last_price("AAPL", 105.0)

        # NAV = 10000 + 500 (realized) + 250 (unrealized) = 10750
        assert accountant.nav == 10750.0

    def test_daily_pnl_property(self, accountant):
        """Test daily_pnl property (NAV - starting capital)."""
        accountant.record_fill_direct("order_1", "AAPL", qty=100.0, fill_price=100.0)
        accountant._update_last_price("AAPL", 105.0)

        assert accountant.daily_pnl == 500.0  # 10500 - 10000

    def test_realized_pnl_property(self, accountant):
        """Test realized_pnl property."""
        accountant.record_fill_direct("order_1", "AAPL", qty=100.0, fill_price=100.0)
        accountant.record_fill_direct("order_2", "AAPL", qty=-100.0, fill_price=115.0)

        assert accountant.realized_pnl == 1500.0  # 100 * (115 - 100)

    def test_nav_property_consistency(self, accountant):
        """Test nav property is consistent (readable as property)."""
        accountant.record_fill_direct("order_1", "AAPL", qty=10.0, fill_price=150.0)
        accountant._update_last_price("AAPL", 155.0)

        # Both should work and be equal
        nav_property = accountant.nav
        nav_method = accountant.nav_property()
        assert nav_property == nav_method


class TestMarkToMarket:
    """Tests for mark_to_market integration with new methods."""

    def test_mark_to_market_updates_last_prices(self, accountant):
        """Test mark_to_market updates internal last prices."""
        accountant.record_fill_direct("order_1", "AAPL", qty=10.0, fill_price=150.0)
        accountant.mark_to_market({"AAPL": 155.0})

        assert accountant._last_price["AAPL"] == 155.0

    def test_mark_to_market_with_new_fill_tracking(self, accountant):
        """Test mark_to_market works correctly with new fill_direct method."""
        accountant.record_fill_direct("order_1", "AAPL", qty=100.0, fill_price=100.0)
        nav_after_buy = accountant.mark_to_market({"AAPL": 105.0})

        # NAV should be 10500 (gain of 500 on position)
        assert nav_after_buy == 10500.0

    def test_mark_to_market_multiple_updates(self, accountant):
        """Test multiple mark_to_market calls."""
        accountant.record_fill_direct("order_1", "AAPL", qty=100.0, fill_price=100.0)

        nav1 = accountant.mark_to_market({"AAPL": 105.0})
        nav2 = accountant.mark_to_market({"AAPL": 110.0})
        nav3 = accountant.mark_to_market({"AAPL": 102.0})

        assert nav1 == 10500.0
        assert nav2 == 11000.0
        assert nav3 == 10200.0


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_zero_quantity_position_removed_from_tracking(self, accountant):
        """Test that positions with qty=0 are properly handled."""
        accountant.record_fill_direct("order_1", "AAPL", qty=10.0, fill_price=150.0)
        accountant.record_fill_direct("order_2", "AAPL", qty=-10.0, fill_price=160.0)

        # Position should be closed
        assert accountant._positions["AAPL"]["quantity"] == 0.0
        assert "AAPL" not in accountant.current_positions

    def test_multiple_open_closes_same_symbol(self, accountant):
        """Test multiple open/close cycles on same symbol."""
        # Cycle 1: Buy 10 at 100, sell 10 at 110 (gain of 100)
        accountant.record_fill_direct("order_1", "AAPL", qty=10.0, fill_price=100.0)
        accountant.record_fill_direct("order_2", "AAPL", qty=-10.0, fill_price=110.0)
        assert accountant.realized_pnl == 100.0

        # Cycle 2: Buy 10 at 120, sell 10 at 115 (loss of 50)
        accountant.record_fill_direct("order_3", "AAPL", qty=10.0, fill_price=120.0)
        accountant.record_fill_direct("order_4", "AAPL", qty=-10.0, fill_price=115.0)

        # Total realized PnL = 100 + (-50) = 50
        # -50 because: 10 * (115 - 120) = -50
        assert accountant.realized_pnl == 50.0

    def test_short_position_tracking(self, accountant):
        """Test tracking of short positions (negative qty)."""
        # Sell short first (starting with no position)
        accountant.record_fill_direct("order_1", "AAPL", qty=-10.0, fill_price=150.0)

        assert accountant._positions["AAPL"]["quantity"] == -10.0
        assert accountant._cost_basis["AAPL"] == 150.0

        # Cover at different price
        accountant._update_last_price("AAPL", 140.0)
        snap = accountant.current_positions["AAPL"]
        assert snap.unrealized_pnl == 100.0  # -10 * (140 - 150)

    def test_default_timestamp_if_not_provided(self, accountant):
        """Test that timestamp defaults to now if not provided."""
        accountant.record_fill_direct("order_1", "AAPL", qty=10.0, fill_price=150.0)

        fill = accountant._fill_log[0]
        assert fill["timestamp"] is not None
        assert isinstance(fill["timestamp"], datetime)

    def test_large_position_tracking(self, accountant):
        """Test tracking large positions."""
        # $500k position
        accountant.record_fill_direct("order_1", "AAPL", qty=5000.0, fill_price=100.0)
        accountant._update_last_price("AAPL", 105.0)

        snap = accountant.current_positions["AAPL"]
        assert snap.notional == 525000.0
        assert snap.unrealized_pnl == 25000.0

    def test_fractional_shares(self, accountant):
        """Test tracking fractional shares."""
        accountant.record_fill_direct(
            "order_1", "AAPL", qty=0.5, fill_price=150.0
        )
        accountant._update_last_price("AAPL", 155.0)

        snap = accountant.current_positions["AAPL"]
        assert snap.qty == 0.5
        assert snap.unrealized_pnl == 2.5  # 0.5 * (155 - 150)

    def test_negative_price_handling(self, accountant):
        """Test that negative prices are still tracked (edge case)."""
        # This shouldn't happen in practice, but code should handle it
        accountant.record_fill_direct("order_1", "TEST", qty=10.0, fill_price=100.0)
        accountant._update_last_price("TEST", -50.0)  # Pathological case

        snap = accountant.current_positions["TEST"]
        assert snap.current_price == -50.0
        assert snap.unrealized_pnl == -1500.0

    def test_pnl_pct_zero_cost_basis(self, accountant):
        """Test pnl_pct property when cost_basis is zero."""
        accountant.record_fill_direct("order_1", "AAPL", qty=10.0, fill_price=0.0)
        accountant._update_last_price("AAPL", 100.0)

        snap = accountant.current_positions["AAPL"]
        # pnl_pct should return 0.0 when cost_basis is 0
        assert snap.pnl_pct == 0.0


class TestIntegration:
    """Integration tests combining multiple features."""

    def test_full_trading_cycle(self, accountant):
        """Test a complete trading cycle: buy, hold, sell."""
        # Initial state
        assert accountant.nav == 10000.0
        assert accountant.daily_pnl == 0.0

        # Day 1: Buy 100 AAPL at $100
        accountant.record_fill_direct("order_1", "AAPL", qty=100.0, fill_price=100.0)
        accountant._update_last_price("AAPL", 100.0)
        assert accountant.nav == 10000.0  # No unrealized gain yet

        # Day 2: Price moves to $105
        accountant._update_last_price("AAPL", 105.0)
        assert accountant.nav == 10500.0
        assert accountant.daily_pnl == 500.0

        # Day 3: Sell 50 at $108
        # Realized: 50 * (108 - 100) = 400 on closed portion
        # Remaining: 50 @ avg cost 100, current price 108
        accountant.record_fill_direct("order_2", "AAPL", qty=-50.0, fill_price=108.0)
        accountant._update_last_price("AAPL", 108.0)
        assert accountant.realized_pnl == 400.0
        # Unrealized: 50 * (108 - 100) = 400
        # NAV = 10000 + 400 (realized) + 400 (unrealized) = 10800
        assert accountant.nav == 10800.0

        # Day 4: Sell remaining 50 at $110
        # Realized: 400 + 50*(110-100) = 900
        accountant.record_fill_direct("order_3", "AAPL", qty=-50.0, fill_price=110.0)
        accountant._update_last_price("AAPL", 110.0)
        assert accountant.realized_pnl == 900.0
        # NAV = 10000 + 900 = 10900
        assert accountant.nav == 10900.0
        assert "AAPL" not in accountant.current_positions

    def test_multi_symbol_portfolio(self, accountant):
        """Test managing a portfolio with multiple symbols."""
        # Portfolio: 100 AAPL, 50 MSFT, 200 GOOGL
        accountant.record_fill_direct("order_1", "AAPL", qty=100.0, fill_price=150.0)
        accountant.record_fill_direct("order_2", "MSFT", qty=50.0, fill_price=300.0)
        accountant.record_fill_direct("order_3", "GOOGL", qty=200.0, fill_price=100.0)

        # Update prices: all up 5%
        accountant._update_last_price("AAPL", 157.5)
        accountant._update_last_price("MSFT", 315.0)
        accountant._update_last_price("GOOGL", 105.0)

        positions = accountant.current_positions
        # Total unrealized gain: 100*7.5 + 50*15 + 200*5 = 750 + 750 + 1000 = 2500
        total_unrealized = sum(p.unrealized_pnl for p in positions.values())
        assert total_unrealized == 2500.0
        assert accountant.nav == 12500.0
