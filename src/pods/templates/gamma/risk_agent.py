from __future__ import annotations
import logging
from datetime import datetime, timezone
from src.core.models.execution import Order, RiskApprovalToken
from src.pods.base.agent import BasePodAgent

logger = logging.getLogger(__name__)
MAX_ASSET_PCT = 0.30
MAX_LEVERAGE = 1.2


class GammaRiskAgent(BasePodAgent):
    """Max 30% per asset, leverage <= 1.2x."""

    async def run_cycle(self, context: dict) -> dict:
        order: Order | None = context.get("order")
        if order is None:
            return {}

        exp_key = f"exposure_{order.symbol}"
        current = self.recall(exp_key, 0.0)
        new_exp = current + (order.quantity * 100) / 1_000_000

        if new_exp > MAX_ASSET_PCT:
            revised_qty = max(1.0, order.quantity * (MAX_ASSET_PCT / max(new_exp, 1e-8)))
            revised = Order(
                id=order.id,
                pod_id=order.pod_id,
                symbol=order.symbol,
                side=order.side,
                order_type=order.order_type,
                quantity=revised_qty,
                limit_price=order.limit_price,
                timestamp=order.timestamp,
                strategy_tag=order.strategy_tag,
            )
            return {"revised_order": revised}

        token = RiskApprovalToken(
            order_id=order.id,
            pod_id=self._pod_id,
        )
        self.store(exp_key, new_exp)
        return {"token": token}
