"""Intraday position monitor — checks positions against exit conditions every cycle."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from src.core.models.enums import Side, OrderType
from src.core.models.execution import Order

logger = logging.getLogger(__name__)


class PositionMonitor:
    """Lightweight monitor that checks open positions against stored exit conditions.

    Runs every cycle in session_manager (between mark-to-market and governance).
    Catches stop-loss, take-profit, and max-hold-days breaches between daily reviews.
    """

    def check_positions(self, accountant, current_prices: dict | None = None) -> list[Order]:
        """Return exit orders for positions that breach their limits.

        Args:
            accountant: PortfolioAccountant with current_positions and _entry_metadata.
            current_prices: optional price overrides (sym -> price).
        """
        exit_orders: list[Order] = []
        today = datetime.now(timezone.utc).date()

        for sym, snap in accountant.current_positions.items():
            if snap.qty == 0 or snap.cost_basis <= 0:
                continue

            price = (current_prices or {}).get(sym, snap.current_price)
            direction = 1 if snap.qty > 0 else -1
            pnl_pct = direction * (price - snap.cost_basis) / snap.cost_basis

            meta = accountant._entry_metadata.get(sym, {})
            sl = meta.get("stop_loss_pct", 0.05)
            tp = meta.get("take_profit_pct", 0.15)
            tp_levels = self._take_profit_levels(meta.get("take_profit_levels"))
            tp_hits = set(int(x) for x in meta.get("take_profit_hits", []) if str(x).isdigit())
            max_days = meta.get("max_hold_days", 0)
            entry_time_str = meta.get("entry_time", "")

            reason = ""
            exit_qty = abs(snap.qty)
            strategy_tag = "position_monitor_exit"
            if pnl_pct < -sl:
                reason = f"Position monitor: stop-loss {sym} at {pnl_pct:+.2%} (limit -{sl:.0%})"
            else:
                for idx, level in enumerate(tp_levels):
                    if idx in tp_hits:
                        continue
                    trigger = float(level.get("trigger_pct", 0) or 0)
                    if pnl_pct >= trigger:
                        close_pct = float(level.get("close_pct", 0) or 0)
                        exit_qty = max(0.0, min(abs(snap.qty), abs(snap.qty) * close_pct))
                        if exit_qty <= 1e-9:
                            continue
                        meta.setdefault("take_profit_hits", []).append(idx)
                        label = level.get("label") or f"TP{idx + 1}"
                        strategy_tag = f"position_monitor_tp{idx + 1}"
                        reason = (
                            f"Position monitor: {label} {sym} at {pnl_pct:+.2%} "
                            f"(trigger +{trigger:.0%}); closing {close_pct:.0%}"
                        )
                        break
            if not reason and not tp_levels and pnl_pct > tp:
                reason = f"Position monitor: take-profit {sym} at {pnl_pct:+.2%} (limit +{tp:.0%})"
            elif not reason and max_days and entry_time_str:
                try:
                    entry_dt = datetime.fromisoformat(entry_time_str)
                    days_held = (today - entry_dt.date()).days
                    if days_held > max_days:
                        reason = f"Position monitor: max hold exceeded {sym} ({days_held}d > {max_days}d limit)"
                except (ValueError, TypeError):
                    pass

            if reason:
                side = Side.SELL if snap.qty > 0 else Side.BUY
                order = Order(
                    id=uuid.uuid4(),
                    pod_id=accountant._pod_id,
                    symbol=sym,
                    side=side,
                    order_type=OrderType.MARKET,
                    quantity=exit_qty,
                    timestamp=datetime.now(timezone.utc),
                    strategy_tag=strategy_tag,
                    conviction=1.0,
                )
                exit_orders.append(order)
                logger.info("[position_monitor] %s", reason)

        return exit_orders

    @staticmethod
    def _take_profit_levels(raw_levels: object) -> list[dict]:
        if not isinstance(raw_levels, list):
            return []
        levels: list[dict] = []
        for raw in raw_levels:
            if not isinstance(raw, dict):
                continue
            try:
                trigger = float(raw.get("trigger_pct", 0) or 0)
                close_pct = float(raw.get("close_pct", 0) or 0)
            except (TypeError, ValueError):
                continue
            if trigger <= 0 or close_pct <= 0:
                continue
            levels.append({
                "trigger_pct": trigger,
                "close_pct": min(close_pct, 1.0),
                "label": raw.get("label", ""),
            })
        return sorted(levels, key=lambda x: x["trigger_pct"])
