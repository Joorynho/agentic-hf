from __future__ import annotations
import logging
from datetime import datetime, timezone
from src.core.models.execution import Order, RiskApprovalToken
from src.pods.base.agent import BasePodAgent

logger = logging.getLogger(__name__)

MAX_PAIR_EXPOSURE_PCT = 0.25  # max 25% of NAV per pair


class BetaRiskAgent(BasePodAgent):
    """Validates pair exposure limits and issues RiskApprovalToken."""

    async def run_cycle(self, context: dict) -> dict:
        order: Order | None = context.get("order")
        if order is None:
            return {}

        # Derive pair tag from strategy_tag (e.g. "entry_XLK_XLF" → "XLK_XLF")
        parts = order.strategy_tag.split("_", 1)
        pair_tag = parts[1] if len(parts) == 2 else order.strategy_tag
        exposure_key = f"exposure_{pair_tag}"
        current_exposure = self.recall(exposure_key, 0.0)
        # Assume $1 M NAV; each share ~$100 notional
        new_exposure = current_exposure + (order.quantity * 100) / 1_000_000

        if new_exposure > MAX_PAIR_EXPOSURE_PCT:
            max_units = (MAX_PAIR_EXPOSURE_PCT - current_exposure) * 1_000_000 / 100
            revised_qty = max(1.0, max_units)
            logger.info(
                "[beta.risk] Exposure breach → revising qty %.0f → %.0f",
                order.quantity, revised_qty,
            )
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

        # Approve: issue a short-lived token
        token = RiskApprovalToken(
            order_id=order.id,
            pod_id=self._pod_id,
            expires_ms=500,
        )
        self.store(exposure_key, new_exposure)
        logger.debug("[beta.risk] Approved order %s", order.id)
        return {"token": token}
