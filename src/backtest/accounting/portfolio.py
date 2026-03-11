from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.core.models.execution import Fill, Position, PositionSnapshot
from src.core.models.enums import Side

logger = logging.getLogger(__name__)


class PortfolioAccountant:
    def __init__(self, pod_id: str, initial_nav: float):
        self._pod_id = pod_id
        self._starting_capital = initial_nav
        self._cash = initial_nav
        self._positions: dict[str, dict] = {}
        self._cost_basis: dict[str, float] = {}
        self._last_price: dict[str, float] = {}
        self._hwm = initial_nav
        self._nav_history: list[float] = [initial_nav]
        self._realized_pnl = 0.0
        self._fill_log: list[dict] = []

    def record_fill(self, fill: Fill) -> None:
        """Record a fill from the execution layer (original method - updated to track cost basis)."""
        sym = fill.symbol
        if sym not in self._positions:
            self._positions[sym] = {
                "quantity": 0.0,
                "avg_cost": 0.0,
                "market_value": 0.0,
                "unrealised_pnl": 0.0,
            }
            self._cost_basis[sym] = 0.0
        pos = self._positions[sym]
        if fill.side == Side.BUY:
            total_cost = pos["quantity"] * pos["avg_cost"] + fill.quantity * fill.price
            pos["quantity"] += fill.quantity
            pos["avg_cost"] = total_cost / pos["quantity"] if pos["quantity"] else 0
            self._cost_basis[sym] = pos["avg_cost"]
            self._cash -= fill.quantity * fill.price + fill.commission
        else:
            pos["quantity"] -= fill.quantity
            if pos["quantity"] == 0:
                self._cost_basis[sym] = 0.0
            self._cash += fill.quantity * fill.price - fill.commission
            if pos["quantity"] == 0:
                del self._positions[sym]

    def record_fill_direct(
        self,
        order_id: str,
        symbol: str,
        qty: float,
        fill_price: float,
        filled_at: datetime | None = None,
    ) -> None:
        """
        Record an order fill from OrderResult. Updates positions and cost basis.

        Args:
            order_id: Unique order identifier
            symbol: Stock symbol (e.g., 'AAPL')
            qty: Filled quantity (positive for BUY, negative for SELL)
            fill_price: Price at which order was filled
            filled_at: Timestamp of fill (default: now)
        """
        if filled_at is None:
            filled_at = datetime.now(timezone.utc)

        # Initialize position if new
        if symbol not in self._positions:
            self._positions[symbol] = {
                "quantity": 0.0,
                "avg_cost": 0.0,
                "market_value": 0.0,
                "unrealised_pnl": 0.0,
            }
            self._cost_basis[symbol] = 0.0

        pos = self._positions[symbol]
        prev_qty = pos["quantity"]
        prev_cost = self._cost_basis[symbol]
        new_qty = prev_qty + qty

        # Calculate realized PnL for any position reduction
        if (prev_qty > 0 and qty < 0) or (prev_qty < 0 and qty > 0):
            # We're reducing or closing a position
            # Only the reduced portion realizes PnL
            reduced_qty = min(abs(qty), abs(prev_qty))
            realized = reduced_qty * (fill_price - prev_cost)
            if prev_qty < 0:
                # Short position: profit when price falls
                realized = -realized
            self._realized_pnl += realized
            logger.info(
                f"[{self._pod_id}] Realized PnL on {symbol}: ${realized:.2f}"
            )

        # Update cost basis using weighted average
        if new_qty == 0:
            # Closing position entirely
            self._cost_basis[symbol] = 0.0
        elif prev_qty == 0:
            # Opening new position
            self._cost_basis[symbol] = fill_price
        else:
            # Same direction (adding to position): update weighted average
            if (prev_qty > 0 and qty > 0) or (prev_qty < 0 and qty < 0):
                old_notional = prev_qty * prev_cost
                new_notional = qty * fill_price
                self._cost_basis[symbol] = (old_notional + new_notional) / new_qty

        # Update position
        pos["quantity"] = new_qty
        pos["avg_cost"] = self._cost_basis[symbol]

        # Log fill in audit trail
        self._fill_log.append(
            {
                "timestamp": filled_at,
                "order_id": order_id,
                "symbol": symbol,
                "qty": qty,
                "fill_price": fill_price,
                "notional": qty * fill_price,
            }
        )

        logger.debug(
            f"[{self._pod_id}] Fill recorded: {symbol} {qty:+.1f} @ ${fill_price:.2f}"
        )

    def _update_last_price(self, symbol: str, price: float) -> None:
        """Update market price for symbol (called during bar push)."""
        self._last_price[symbol] = price

    @property
    def current_positions(self) -> dict[str, PositionSnapshot]:
        """
        Get all open positions with current market prices.

        Returns:
            dict mapping symbol to PositionSnapshot
        """
        positions = {}
        for symbol, qty in [
            (s, p["quantity"]) for s, p in self._positions.items()
        ]:
            if qty != 0:
                current_price = self._last_price.get(
                    symbol, self._cost_basis.get(symbol, 0.0)
                )
                unrealized_pnl = qty * (current_price - self._cost_basis.get(symbol, 0.0))
                positions[symbol] = PositionSnapshot(
                    symbol=symbol,
                    qty=qty,
                    cost_basis=self._cost_basis.get(symbol, 0.0),
                    current_price=current_price,
                    unrealized_pnl=unrealized_pnl,
                )
        return positions

    @property
    def nav(self) -> float:
        """
        Net Asset Value = initial capital + unrealized PnL + realized PnL
        """
        unrealized = sum(
            snapshot.unrealized_pnl for snapshot in self.current_positions.values()
        )
        return self._starting_capital + self._realized_pnl + unrealized

    @property
    def daily_pnl(self) -> float:
        """Profit/loss since session start (includes both realized and unrealized)."""
        return self.nav - self._starting_capital

    @property
    def starting_capital(self) -> float:
        return self._starting_capital

    @property
    def realized_pnl(self) -> float:
        """PnL from closed positions."""
        return self._realized_pnl

    def mark_to_market(self, prices: dict[str, float]) -> float:
        # Update last prices first
        for sym, price in prices.items():
            self._update_last_price(sym, price)

        # Update position market values and unrealized PnL
        total_market_value = 0.0
        for sym, pos in self._positions.items():
            price = prices.get(sym, pos["avg_cost"])
            pos["market_value"] = pos["quantity"] * price
            pos["unrealised_pnl"] = pos["quantity"] * (price - pos["avg_cost"])
            total_market_value += pos["market_value"]

        # NAV includes unrealized from current_positions property
        nav = self.nav
        self._hwm = max(self._hwm, nav)
        self._nav_history.append(nav)
        return nav

    def get_position(self, symbol: str) -> Position | None:
        pos = self._positions.get(symbol)
        if not pos:
            return None
        return Position(
            pod_id=self._pod_id,
            symbol=symbol,
            quantity=pos["quantity"],
            avg_cost=pos["avg_cost"],
            market_value=pos["market_value"],
            unrealised_pnl=pos["unrealised_pnl"],
            last_updated=datetime.now(),
        )

    def nav_property(self) -> float:
        """Legacy method - use nav property instead."""
        return self.nav

    def drawdown_from_hwm(self) -> float:
        if self._hwm == 0:
            return 0.0
        return (self.nav - self._hwm) / self._hwm

    def all_positions(self) -> list[Position]:
        return [self.get_position(s) for s in self._positions if self.get_position(s)]
