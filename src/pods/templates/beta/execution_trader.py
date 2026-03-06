from __future__ import annotations
import logging
from src.core.models.execution import Order, RiskApprovalToken
from src.pods.base.agent import BasePodAgent

logger = logging.getLogger(__name__)


class BetaExecutionTrader(BasePodAgent):
    """Validates RiskApprovalToken then records order for paper adapter."""

    async def run_cycle(self, context: dict) -> dict:
        order: Order | None = context.get("approved_order")
        if order is None:
            return {}

        token: RiskApprovalToken | None = self.recall("last_risk_token")
        if token is None or not token.is_valid():
            logger.warning(
                "[beta.exec] Invalid/expired token — order %s rejected", order.id
            )
            return {"execution_rejected": True}

        # Record for paper adapter (backtest runner collects from namespace)
        pending = self.recall("pending_orders", [])
        pending.append(order.model_dump(mode="json"))
        self.store("pending_orders", pending)
        logger.info(
            "[beta.exec] Order queued: %s %.0f %s",
            order.side, order.quantity, order.symbol,
        )
        return {"order_queued": True}
