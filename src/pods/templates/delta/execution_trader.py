from __future__ import annotations
import logging
from src.core.models.execution import Order, RiskApprovalToken
from src.pods.base.agent import BasePodAgent

logger = logging.getLogger(__name__)


class DeltaExecutionTrader(BasePodAgent):
    """Token-gated order queuing. Enforces 5-day auto-expiry via PM."""

    async def run_cycle(self, context: dict) -> dict:
        order: Order | None = context.get("approved_order")
        if order is None:
            return {}
        token: RiskApprovalToken | None = self.recall("last_risk_token")
        if token is None or not token.is_valid():
            logger.warning("[delta.exec] Invalid/expired token — order %s rejected", order.id)
            return {"execution_rejected": True}
        pending = self.recall("pending_orders", [])
        pending.append(order.model_dump(mode="json"))
        self.store("pending_orders", pending)
        logger.info("[delta.exec] Queued: %s %s %s", order.side, order.quantity, order.symbol)
        return {"order_queued": True}
