from __future__ import annotations
import logging
import uuid
from datetime import datetime, timezone
from src.core.models.enums import Side, OrderType
from src.core.models.execution import Order, RiskApprovalToken
from src.core.models.messages import AgentMessage
from src.pods.base.agent import BasePodAgent

logger = logging.getLogger(__name__)

MAX_LEVERAGE = 2.0
MIN_FRACTIONAL_QTY = 0.01
STOP_LOSS_PCT = 0.05
TAKE_PROFIT_PCT = 0.15


def _conviction_limit(conviction: float) -> float:
    """Position limit as % of NAV, scaled by conviction (10% at 0.0, 25% at 1.0)."""
    return 0.10 + 0.15 * max(0.0, min(1.0, conviction))


class FXRiskAgent(BasePodAgent):
    """Position-level risk checks for FX."""

    def _check_stop_loss_take_profit(self, accountant) -> list[Order]:
        exit_orders: list[Order] = []
        regime = self._ns.get("market_regime") or {}
        regime_label = regime.get("label", "").lower()
        sl_pct = 0.03 if "crisis" in regime_label else STOP_LOSS_PCT

        for sym, snap in accountant.current_positions.items():
            if snap.cost_basis <= 0 or snap.qty == 0:
                continue
            meta = accountant._entry_metadata.get(sym, {})
            pos_sl = meta.get("stop_loss_pct", sl_pct)
            pos_tp = meta.get("take_profit_pct", TAKE_PROFIT_PCT)
            pnl_pct = (snap.current_price - snap.cost_basis) / snap.cost_basis

            reason = ""
            if pnl_pct < -pos_sl:
                reason = f"Stop-loss triggered: {sym} at {pnl_pct:+.2%} (limit -{pos_sl:.0%})"
            elif pnl_pct > pos_tp:
                reason = f"Take-profit triggered: {sym} at {pnl_pct:+.2%} (limit +{pos_tp:.0%})"

            if reason:
                side = Side.SELL if snap.qty > 0 else Side.BUY
                order = Order(
                    id=uuid.uuid4(), pod_id=self._pod_id, symbol=sym,
                    side=side, order_type=OrderType.MARKET,
                    quantity=abs(snap.qty), timestamp=datetime.now(timezone.utc),
                    strategy_tag="risk_auto_exit", conviction=1.0,
                )
                exit_orders.append(order)
                logger.info("[fx.risk] %s", reason)
        return exit_orders

    async def run_cycle(self, context: dict) -> dict:
        order: Order | None = context.get("order")
        if order is None:
            return {}

        accountant = self._ns.get("accountant")
        if not accountant:
            token = RiskApprovalToken(order_id=order.id, pod_id=self._pod_id, expires_ms=500)
            await self._broadcast("risk_approval", order, f"Approved {order.side.value} {order.quantity:.2f} {order.symbol} (no accountant)")
            return {"token": token}

        exit_orders = self._check_stop_loss_take_profit(accountant)
        for eo in exit_orders:
            await self._broadcast("risk_auto_exit", eo, f"Auto-exit {eo.side.value} {eo.quantity:.2f} {eo.symbol}")

        nav = accountant.nav
        existing = accountant.current_positions.get(order.symbol)
        existing_qty = existing.qty if existing else 0.0
        est_price = (
            existing.current_price if existing
            else accountant.get_last_price(order.symbol, 100.0)
        )

        # --- Position limit check (conviction-scaled) ---
        conviction = getattr(order, "conviction", 0.5)
        regime = self._ns.get("market_regime") or {}
        regime_scale = regime.get("scale", 1.0)
        max_position_pct = min(0.30, _conviction_limit(conviction) * regime_scale)
        signed_qty = order.quantity if order.side == Side.BUY else -order.quantity
        new_qty = existing_qty + signed_qty
        new_notional = abs(new_qty) * est_price
        if nav > 0 and new_notional / nav > max_position_pct:
            max_notional = max_position_pct * nav
            max_qty = max_notional / est_price if est_price > 0 else 0
            if order.side == Side.BUY:
                max_qty = max(0, max_qty - existing_qty)
            else:
                max_qty = max(0, existing_qty - max_qty)
            if max_qty < MIN_FRACTIONAL_QTY:
                reason = f"Position limit ({max_position_pct*100:.0f}% NAV=${nav:.2f}, conv={conviction:.1f}). No feasible size for {order.symbol}."
                logger.info("[fx.risk] %s", reason)
                await self._broadcast("risk_rejection", order, reason)
                return {"reason": reason}
            revised = Order(
                id=order.id, pod_id=order.pod_id, symbol=order.symbol,
                side=order.side, order_type=order.order_type,
                quantity=round(max_qty, 4), limit_price=order.limit_price,
                timestamp=order.timestamp, strategy_tag=order.strategy_tag,
                conviction=conviction,
            )
            reason = f"Position limit: {order.side.value} {order.symbol} {order.quantity:.2f} -> {revised.quantity:.2f} ({max_position_pct*100:.0f}% of NAV=${nav:.2f}, conv={conviction:.1f})"
            logger.info("[fx.risk] %s", reason)
            await self._broadcast("risk_revision", order, reason, revised_qty=revised.quantity)
            return {"revised_order": revised, "reason": reason}

        # --- Leverage check ---
        total_notional = sum(abs(s.qty * s.current_price) for s in accountant.current_positions.values())
        order_notional = order.quantity * est_price
        projected_notional = total_notional + order_notional
        if nav > 0 and projected_notional / nav > MAX_LEVERAGE:
            max_add = MAX_LEVERAGE * nav - total_notional
            if max_add < MIN_FRACTIONAL_QTY * est_price:
                reason = f"Leverage limit ({MAX_LEVERAGE:.1f}x, NAV=${nav:.2f}). No room for {order.symbol}."
                logger.info("[fx.risk] %s", reason)
                await self._broadcast("risk_rejection", order, reason)
                return {"reason": reason}
            max_qty_lev = max_add / est_price if est_price > 0 else 0
            revised = Order(
                id=order.id, pod_id=order.pod_id, symbol=order.symbol,
                side=order.side, order_type=order.order_type,
                quantity=round(max(MIN_FRACTIONAL_QTY, max_qty_lev), 4), limit_price=order.limit_price,
                timestamp=order.timestamp, strategy_tag=order.strategy_tag,
                conviction=conviction,
            )
            reason = f"Leverage limit: {order.side.value} {order.symbol} {order.quantity:.2f} -> {revised.quantity:.2f} ({MAX_LEVERAGE:.1f}x max)"
            logger.info("[fx.risk] %s", reason)
            await self._broadcast("risk_revision", order, reason, revised_qty=revised.quantity)
            return {"revised_order": revised, "reason": reason}

        # --- Approved ---
        token = RiskApprovalToken(order_id=order.id, pod_id=self._pod_id, expires_ms=500)
        await self._broadcast("risk_approval", order, f"Approved {order.side.value} {order.quantity:.2f} {order.symbol}")
        result: dict = {"token": token}
        if exit_orders:
            result["exit_orders"] = exit_orders
        return result

    async def _broadcast(self, action: str, order: Order, summary: str, revised_qty: float | None = None) -> None:
        try:
            msg = AgentMessage(
                timestamp=datetime.now(timezone.utc),
                sender=self._agent_id,
                recipient="dashboard",
                topic="agent.activity",
                payload={
                    "agent_id": self._agent_id,
                    "agent_role": "Risk",
                    "pod_id": self._pod_id,
                    "action": action,
                    "summary": summary,
                    "detail": f"symbol={order.symbol} side={order.side.value} original_qty={order.quantity:.2f}" + (f" revised_qty={revised_qty:.2f}" if revised_qty else ""),
                },
            )
            await self._bus.publish("agent.activity", msg, publisher_id=self._agent_id)
        except Exception:
            pass
