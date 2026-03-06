from __future__ import annotations
import logging
from datetime import datetime, timezone
from src.core.models.execution import Order, RiskApprovalToken
from src.pods.base.agent import BasePodAgent

logger = logging.getLogger(__name__)
MAX_VOL_EXPOSURE = 0.50  # max 50% of NAV in any single vol product


class EpsilonRiskAgent(BasePodAgent):
    """Strict vol-of-vol limits. VXX auto-halved at Extreme regime."""

    async def run_cycle(self, context: dict) -> dict:
        order: Order | None = context.get("order")
        if order is None:
            return {}

        regime = self.recall("regime", "normal")
        qty = order.quantity

        # Auto-halve VXX in extreme regime (additional safety)
        if regime == "extreme" and order.symbol == "VXX":
            qty = qty * 0.5
            logger.info("[epsilon.risk] Extreme regime -> VXX qty halved to %.0f", qty)

        exp_key = f"exposure_{order.symbol}"
        current = self.recall(exp_key, 0.0)
        new_exp = current + (qty * 100) / 1_000_000

        if new_exp > MAX_VOL_EXPOSURE:
            revised_qty = max(1.0, qty * (MAX_VOL_EXPOSURE / max(new_exp, 1e-8)))
            revised = Order(
                id=order.id, pod_id=order.pod_id, symbol=order.symbol,
                side=order.side, order_type=order.order_type,
                quantity=revised_qty, limit_price=order.limit_price,
                timestamp=order.timestamp, strategy_tag=order.strategy_tag,
            )
            return {"revised_order": revised}

        token = RiskApprovalToken(pod_id=self._pod_id, order_id=order.id)
        self.store(exp_key, new_exp)
        return {"token": token}
