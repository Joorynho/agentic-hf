from __future__ import annotations

from datetime import datetime

from src.core.models.execution import Fill, Position
from src.core.models.enums import Side


class PortfolioAccountant:
    def __init__(self, pod_id: str, initial_nav: float):
        self._pod_id = pod_id
        self._cash = initial_nav
        self._positions: dict[str, dict] = {}
        self._hwm = initial_nav
        self._nav_history: list[float] = [initial_nav]

    def record_fill(self, fill: Fill) -> None:
        sym = fill.symbol
        if sym not in self._positions:
            self._positions[sym] = {
                "quantity": 0.0,
                "avg_cost": 0.0,
                "market_value": 0.0,
                "unrealised_pnl": 0.0,
            }
        pos = self._positions[sym]
        if fill.side == Side.BUY:
            total_cost = pos["quantity"] * pos["avg_cost"] + fill.quantity * fill.price
            pos["quantity"] += fill.quantity
            pos["avg_cost"] = total_cost / pos["quantity"] if pos["quantity"] else 0
            self._cash -= fill.quantity * fill.price + fill.commission
        else:
            pos["quantity"] -= fill.quantity
            self._cash += fill.quantity * fill.price - fill.commission
            if pos["quantity"] == 0:
                del self._positions[sym]

    def mark_to_market(self, prices: dict[str, float]) -> float:
        total_market_value = 0.0
        for sym, pos in self._positions.items():
            price = prices.get(sym, pos["avg_cost"])
            pos["market_value"] = pos["quantity"] * price
            pos["unrealised_pnl"] = pos["quantity"] * (price - pos["avg_cost"])
            total_market_value += pos["market_value"]
        nav = self._cash + total_market_value
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

    def nav(self) -> float:
        return self._nav_history[-1] if self._nav_history else 0

    def drawdown_from_hwm(self) -> float:
        if self._hwm == 0:
            return 0.0
        return (self.nav() - self._hwm) / self._hwm

    def all_positions(self) -> list[Position]:
        return [self.get_position(s) for s in self._positions if self.get_position(s)]
