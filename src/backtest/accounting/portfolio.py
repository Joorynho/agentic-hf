from __future__ import annotations

import logging
import math
from datetime import date, datetime, timezone

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
        self._entry_theses: dict[str, str] = {}
        self._entry_dates: dict[str, str] = {}
        self._entry_metadata: dict[str, dict] = {}
        self._closed_trades: list[dict] = []
        self._position_reasoning_log: dict[str, list[dict]] = {}
        self._daily_nav_snapshots: list[tuple[date, float]] = [(date.today(), initial_nav)]

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
        reasoning: str = "",
        strategy_tag: str = "",
        signal_snapshot: dict | None = None,
        conviction: float = 0.5,
        stop_loss_pct: float | None = None,
        take_profit_pct: float | None = None,
        exit_when: str = "",
        max_hold_days: int = 0,
    ) -> None:
        """
        Record an order fill from OrderResult. Updates positions and cost basis.

        Args:
            order_id: Unique order identifier
            symbol: Stock symbol (e.g., 'AAPL')
            qty: Filled quantity (positive for BUY, negative for SELL)
            fill_price: Price at which order was filled
            filled_at: Timestamp of fill (default: now)
            reasoning: PM reasoning for the trade
            strategy_tag: Strategy identifier (e.g., 'macro_momentum')
            signal_snapshot: Signal state at trade time
            conviction: PM conviction score (0-1)
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

        # Store entry metadata when opening a new position
        if prev_qty == 0 and qty != 0:
            self._entry_theses[symbol] = reasoning or ""
            self._entry_dates[symbol] = filled_at.strftime("%Y-%m-%d") if filled_at else ""
            self._entry_metadata[symbol] = {
                "entry_price": fill_price,
                "entry_time": filled_at.isoformat() if filled_at else "",
                "reasoning": reasoning,
                "conviction": conviction,
                "strategy_tag": strategy_tag,
                "signal_snapshot": signal_snapshot or {},
                "stop_loss_pct": stop_loss_pct if stop_loss_pct is not None else 0.05,
                "take_profit_pct": take_profit_pct if take_profit_pct is not None else 0.15,
                "exit_when": exit_when,
                "max_hold_days": max_hold_days,
            }

        # Calculate realized PnL for any position reduction
        if (prev_qty > 0 and qty < 0) or (prev_qty < 0 and qty > 0):
            reduced_qty = min(abs(qty), abs(prev_qty))
            realized = reduced_qty * (fill_price - prev_cost)
            if prev_qty < 0:
                realized = -realized
            self._realized_pnl += realized

            entry_meta = self._entry_metadata.get(symbol, {})
            self._closed_trades.append({
                "symbol": symbol,
                "side": "long" if prev_qty > 0 else "short",
                "entry_price": entry_meta.get("entry_price") or prev_cost,
                "exit_price": fill_price,
                "qty": reduced_qty,
                "realized_pnl": realized,
                "entry_time": entry_meta.get("entry_time", ""),
                "exit_time": filled_at.isoformat() if filled_at else "",
                "entry_reasoning": entry_meta.get("reasoning", ""),
                "exit_reasoning": reasoning if qty < 0 else "",
                "conviction": entry_meta.get("conviction", 0.5),
                "strategy_tag": entry_meta.get("strategy_tag", ""),
                "exit_when": entry_meta.get("exit_when", ""),
                "signal_snapshot": entry_meta.get("signal_snapshot", {}),
            })
            logger.info(
                f"[{self._pod_id}] Closed trade on {symbol}: ${realized:.2f} "
                f"(entry={entry_meta.get('entry_price', prev_cost):.2f}, "
                f"exit={fill_price:.2f})"
            )

        # Update cost basis using weighted average
        if new_qty == 0:
            self._cost_basis[symbol] = 0.0
            self._entry_theses.pop(symbol, None)
            self._entry_dates.pop(symbol, None)
            self._entry_metadata.pop(symbol, None)
            self._position_reasoning_log.pop(symbol, None)
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
                "reasoning": reasoning,
                "strategy_tag": strategy_tag,
                "signal_snapshot": signal_snapshot or {},
                "conviction": conviction,
            }
        )

        logger.debug(
            f"[{self._pod_id}] Fill recorded: {symbol} {qty:+.1f} @ ${fill_price:.2f}"
        )

    def append_reasoning(
        self,
        symbol: str,
        timestamp: str,
        action: str,
        reasoning: str,
        conviction: float = 0.0,
    ) -> None:
        """Append a PM reasoning entry for a held position (capped at 20 per symbol)."""
        if symbol not in self._position_reasoning_log:
            self._position_reasoning_log[symbol] = []
        log = self._position_reasoning_log[symbol]
        log.append({
            "timestamp": timestamp,
            "action": action,
            "reasoning": reasoning,
            "conviction": round(conviction, 2),
        })
        if len(log) > 20:
            self._position_reasoning_log[symbol] = log[-20:]

    def get_reasoning_log(self, symbol: str) -> list[dict]:
        """Return the reasoning history for a symbol (most recent first)."""
        return list(reversed(self._position_reasoning_log.get(symbol, [])))

    def get_last_price(self, symbol: str, default: float = 0.0) -> float:
        """Get the most recent market price for a symbol from bar data."""
        return self._last_price.get(symbol, default)

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
                meta = self._entry_metadata.get(symbol, {})
                positions[symbol] = PositionSnapshot(
                    symbol=symbol,
                    qty=qty,
                    cost_basis=self._cost_basis.get(symbol, 0.0),
                    current_price=current_price,
                    unrealized_pnl=unrealized_pnl,
                    entry_thesis=self._entry_theses.get(symbol, ""),
                    entry_date=self._entry_dates.get(symbol, ""),
                    stop_loss_pct=meta.get("stop_loss_pct", 0.05),
                    take_profit_pct=meta.get("take_profit_pct", 0.15),
                    max_hold_days=meta.get("max_hold_days", 0),
                    conviction=meta.get("conviction", 0.0),
                )
        return positions

    @property
    def closed_trades(self) -> list[dict]:
        """All closed trades with entry metadata and realized PnL."""
        return list(self._closed_trades)

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
        for sym, price in prices.items():
            self._update_last_price(sym, price)

        total_market_value = 0.0
        for sym, pos in self._positions.items():
            price = prices.get(sym, pos["avg_cost"])
            pos["market_value"] = pos["quantity"] * price
            pos["unrealised_pnl"] = pos["quantity"] * (price - pos["avg_cost"])
            total_market_value += pos["market_value"]

        nav = self.nav
        self._hwm = max(self._hwm, nav)
        self._nav_history.append(nav)

        today = date.today()
        if not self._daily_nav_snapshots or self._daily_nav_snapshots[-1][0] != today:
            self._daily_nav_snapshots.append((today, nav))
        else:
            self._daily_nav_snapshots[-1] = (today, nav)

        return nav

    def daily_returns(self, window: int = 20) -> list[float]:
        """Percentage daily returns from NAV snapshots."""
        snaps = self._daily_nav_snapshots[-(window + 1):]
        if len(snaps) < 2:
            return []
        returns = []
        for i in range(1, len(snaps)):
            prev_nav = snaps[i - 1][1]
            if prev_nav > 0:
                returns.append((snaps[i][1] - prev_nav) / prev_nav)
        return returns

    def annualized_volatility(self, window: int = 20) -> float:
        """Annualized volatility from daily NAV returns."""
        rets = self.daily_returns(window)
        if len(rets) < 2:
            return 0.0
        mean = sum(rets) / len(rets)
        variance = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
        return math.sqrt(variance) * math.sqrt(252)

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

    def performance_summary(self) -> dict:
        """Compute Sharpe, Sortino, max drawdown, vol, and total return."""
        from src.core.performance import sharpe_ratio, sortino_ratio, max_drawdown

        rets = self.daily_returns(window=252)
        nav_series = [snap[1] for snap in self._daily_nav_snapshots]
        total_ret = (self.nav - self._starting_capital) / self._starting_capital if self._starting_capital > 0 else 0.0
        return {
            "sharpe": round(sharpe_ratio(rets), 3),
            "sortino": round(sortino_ratio(rets), 3),
            "max_drawdown": round(max_drawdown(nav_series), 4),
            "current_vol": round(self.annualized_volatility(), 4),
            "total_return_pct": round(total_ret * 100, 2),
        }

    # ── Persistence helpers ──────────────────────────────────────────────

    def to_state_dict(self) -> dict:
        """Serialize accountant state for JSON persistence."""
        positions = []
        for sym, pos in self._positions.items():
            if pos["quantity"] != 0:
                positions.append({
                    "symbol": sym,
                    "qty": pos["quantity"],
                    "avg_entry": self._cost_basis.get(sym, pos["avg_cost"]),
                    "current_price": self._last_price.get(sym, pos["avg_cost"]),
                })
        return {
            "pod_id": self._pod_id,
            "nav": round(self.nav, 4),
            "starting_capital": self._starting_capital,
            "daily_pnl": round(self.daily_pnl, 4),
            "realized_pnl": round(self._realized_pnl, 4),
            "cash": round(self._cash, 4),
            "positions": positions,
            "fills": len(self._fill_log),
        }

    def load_positions(self, positions: list[dict]) -> None:
        """Inject positions from Alpaca or memory into the accountant.

        Each dict must have: symbol, qty, avg_entry, current_price.
        Call this BEFORE the first mark_to_market cycle.
        """
        for p in positions:
            sym = p["symbol"]
            qty = float(p["qty"])
            avg_entry = float(p["avg_entry"])
            current_price = float(p.get("current_price", avg_entry))
            if qty == 0:
                continue
            self._positions[sym] = {
                "quantity": qty,
                "avg_cost": avg_entry,
                "market_value": qty * current_price,
                "unrealised_pnl": qty * (current_price - avg_entry),
            }
            self._cost_basis[sym] = avg_entry
            self._last_price[sym] = current_price
        if positions:
            logger.info("[%s] Loaded %d positions from memory/Alpaca", self._pod_id, len(positions))

    def reconcile_capital_from_positions(self, allocated_capital: float | None = None) -> None:
        """Align starting_capital with loaded positions only when they exceed allocation.

        Preserves allocated capital (e.g. $100 per pod): crypto with no positions
        stays at 100; FX with 65 invested keeps NAV=100 and cash=35. Only reconcile
        when hydrated positions exceed allocated_capital (e.g. Alpaca has 50k when
        config allocated 100). Uses allocated_capital if provided, else _starting_capital.
        """
        total_cost = sum(
            abs(p["quantity"]) * self._cost_basis.get(sym, p["avg_cost"])
            for sym, p in self._positions.items()
            if p.get("quantity", 0) != 0
        )
        threshold = allocated_capital if allocated_capital is not None and allocated_capital > 0 else self._starting_capital
        # Keep allocated capital: only reconcile when positions exceed allocation
        if total_cost == 0 or total_cost <= threshold:
            return
        prev = self._starting_capital
        self._starting_capital = total_cost
        logger.info(
            "[%s] Reconciled starting_capital: $%.2f -> $%.2f (%d positions)",
            self._pod_id, prev, total_cost, len([p for p in self._positions.values() if p.get("quantity", 0) != 0]),
        )
