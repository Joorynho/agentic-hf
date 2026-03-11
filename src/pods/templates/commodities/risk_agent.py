from __future__ import annotations
import logging
from src.core.models.enums import Side
from src.core.models.execution import Order, RiskApprovalToken
from src.pods.base.agent import BasePodAgent

logger = logging.getLogger(__name__)

MAX_POSITION_PCT = 0.10  # max 10% per position
MAX_LEVERAGE = 2.0


class CommoditiesRiskAgent(BasePodAgent):
    """Position-level risk checks for commodities."""

    async def run_cycle(self, context: dict) -> dict:
        order: Order | None = context.get("order")
        if order is None:
            return {}

        accountant = self._ns.get("accountant")
        if accountant:
            nav = accountant.nav
            existing = accountant.current_positions.get(order.symbol)
            existing_qty = existing.qty if existing else 0.0
            est_price = existing.current_price if existing else 100.0
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
                if max_qty <= 0:
                    logger.info("[commodities.risk] Position limit hit for %s", order.symbol)
                    return {}
                revised = Order(
                    id=order.id, pod_id=order.pod_id, symbol=order.symbol,
                    side=order.side, order_type=order.order_type,
                    quantity=max(1.0, max_qty), limit_price=order.limit_price,
                    timestamp=order.timestamp, strategy_tag=order.strategy_tag,
                )
                return {"revised_order": revised}

            total_notional = sum(
                abs(s.qty * s.current_price) for s in accountant.current_positions.values()
            )
            order_notional = order.quantity * est_price
            projected_notional = total_notional + order_notional
            if nav > 0 and projected_notional / nav > MAX_LEVERAGE:
                max_add = MAX_LEVERAGE * nav - total_notional
                if max_add <= 0:
                    logger.info("[commodities.risk] Leverage limit hit for %s", order.symbol)
                    return {}
                max_qty_lev = max_add / est_price if est_price > 0 else 0
                revised = Order(
                    id=order.id, pod_id=order.pod_id, symbol=order.symbol,
                    side=order.side, order_type=order.order_type,
                    quantity=max(1.0, max_qty_lev), limit_price=order.limit_price,
                    timestamp=order.timestamp, strategy_tag=order.strategy_tag,
                )
                return {"revised_order": revised}

        token = RiskApprovalToken(
            order_id=order.id, pod_id=self._pod_id, expires_ms=500,
        )
        return {"token": token}
