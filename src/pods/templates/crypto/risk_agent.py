from __future__ import annotations
import logging
from datetime import datetime, timezone
from src.core.models.enums import Side
from src.core.models.execution import Order, RiskApprovalToken
from src.core.models.messages import AgentMessage
from src.pods.base.agent import BasePodAgent

logger = logging.getLogger(__name__)

MAX_POSITION_PCT = 0.15  # crypto is higher vol, slightly tighter limit
MAX_LEVERAGE = 2.0
MIN_FRACTIONAL_QTY = 0.0001  # crypto supports very small fractions


class CryptoRiskAgent(BasePodAgent):
    """Position-level risk checks for crypto. Tighter limits than equities."""

    async def run_cycle(self, context: dict) -> dict:
        order: Order | None = context.get("order")
        if order is None:
            return {}

        accountant = self._ns.get("accountant")
        if not accountant:
            token = RiskApprovalToken(order_id=order.id, pod_id=self._pod_id, expires_ms=500)
            await self._broadcast("risk_approval", order, f"Approved {order.side.value} {order.quantity:.4f} {order.symbol} (no accountant)")
            return {"token": token}

        nav = accountant.nav
        existing = accountant.current_positions.get(order.symbol)
        existing_qty = existing.qty if existing else 0.0
        est_price = (
            existing.current_price if existing
            else accountant.get_last_price(order.symbol, 100.0)
        )

        # --- Position limit check ---
        signed_qty = order.quantity if order.side == Side.BUY else -order.quantity
        new_qty = existing_qty + signed_qty
        new_notional = abs(new_qty) * est_price
        if nav > 0 and new_notional / nav > MAX_POSITION_PCT:
            max_notional = MAX_POSITION_PCT * nav
            max_qty = max_notional / est_price if est_price > 0 else 0
            if order.side == Side.BUY:
                max_qty = max(0, max_qty - existing_qty)
            else:
                max_qty = max(0, existing_qty - max_qty)
            if max_qty < MIN_FRACTIONAL_QTY:
                reason = f"Position limit ({MAX_POSITION_PCT*100:.0f}% NAV=${nav:.2f}). No feasible size for {order.symbol}."
                logger.info("[crypto.risk] %s", reason)
                await self._broadcast("risk_rejection", order, reason)
                return {"reason": reason}
            revised = Order(
                id=order.id, pod_id=order.pod_id, symbol=order.symbol,
                side=order.side, order_type=order.order_type,
                quantity=round(max_qty, 6), limit_price=order.limit_price,
                timestamp=order.timestamp, strategy_tag=order.strategy_tag,
            )
            reason = f"Position limit: {order.side.value} {order.symbol} {order.quantity:.4f} -> {revised.quantity:.4f} ({MAX_POSITION_PCT*100:.0f}% of NAV=${nav:.2f})"
            logger.info("[crypto.risk] %s", reason)
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
                logger.info("[crypto.risk] %s", reason)
                await self._broadcast("risk_rejection", order, reason)
                return {"reason": reason}
            max_qty_lev = max_add / est_price if est_price > 0 else 0
            revised = Order(
                id=order.id, pod_id=order.pod_id, symbol=order.symbol,
                side=order.side, order_type=order.order_type,
                quantity=round(max(MIN_FRACTIONAL_QTY, max_qty_lev), 6), limit_price=order.limit_price,
                timestamp=order.timestamp, strategy_tag=order.strategy_tag,
            )
            reason = f"Leverage limit: {order.side.value} {order.symbol} {order.quantity:.4f} -> {revised.quantity:.4f} ({MAX_LEVERAGE:.1f}x max)"
            logger.info("[crypto.risk] %s", reason)
            await self._broadcast("risk_revision", order, reason, revised_qty=revised.quantity)
            return {"revised_order": revised, "reason": reason}

        # --- Approved ---
        token = RiskApprovalToken(order_id=order.id, pod_id=self._pod_id, expires_ms=500)
        await self._broadcast("risk_approval", order, f"Approved {order.side.value} {order.quantity:.4f} {order.symbol}")
        return {"token": token}

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
                    "detail": f"symbol={order.symbol} side={order.side.value} original_qty={order.quantity}" + (f" revised_qty={revised_qty}" if revised_qty else ""),
                },
            )
            await self._bus.publish("agent.activity", msg, publisher_id=self._agent_id)
        except Exception:
            pass
