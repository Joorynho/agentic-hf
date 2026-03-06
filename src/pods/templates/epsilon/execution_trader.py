from __future__ import annotations
import logging
from datetime import datetime
from typing import Optional

from src.core.models.execution import Order, RiskApprovalToken, OrderResult
from src.execution.paper.alpaca_adapter import AlpacaAdapter
from src.pods.base.agent import BasePodAgent

logger = logging.getLogger(__name__)


class EpsilonExecutionTrader(BasePodAgent):
    """Executes approved orders via Alpaca or queues for paper adapter."""

    def __init__(
        self,
        agent_id: str,
        pod_id: str,
        namespace,
        bus,
        alpaca_adapter: Optional[AlpacaAdapter] = None,
        session_logger=None,
    ):
        super().__init__(agent_id, pod_id, namespace, bus)
        self._alpaca = alpaca_adapter
        self._session_logger = session_logger

    async def run_cycle(self, context: dict) -> dict:
        order: Order | None = context.get("approved_order")
        if order is None:
            return {}
        token: RiskApprovalToken | None = self.recall("last_risk_token")
        if token is None or not token.is_valid():
            logger.warning("[epsilon.exec] Invalid token -- order rejected")
            return {"execution_rejected": True}

        if self._alpaca:
            return await self._execute_via_alpaca(order, token)
        else:
            return self._queue_for_paper_adapter(order)

    async def _execute_via_alpaca(self, order: Order, token: RiskApprovalToken) -> dict:
        """Execute order via Alpaca API."""
        try:
            logger.info(
                "[epsilon.exec] Submitting order to Alpaca: %s %.0f %s @ $%s",
                order.side.value, order.quantity, order.symbol, order.limit_price or "MARKET"
            )

            result_dict = await self._alpaca.place_order(
                symbol=order.symbol,
                qty=order.quantity,
                side=order.side.value,
                order_type="limit" if order.order_type.value == "limit" else "market",
                limit_price=order.limit_price,
            )

            result = OrderResult(
                order_id=result_dict.get("order_id"),
                symbol=order.symbol,
                qty=order.quantity,
                side=order.side.value,
                status=result_dict.get("status", "REJECTED"),
                fill_price=result_dict.get("filled_avg_price"),
                fill_qty=result_dict.get("filled_qty", 0.0),
                reason=None if result_dict.get("status") != "REJECTED" else "Order rejected",
                filled_at=result_dict.get("filled_at"),
            )

            if result.status in ("FILLED", "PARTIAL"):
                logger.info(
                    "[epsilon.exec] Order %s: %s %.0f %s @ $%.2f (id=%s)",
                    result.status, order.symbol, result.fill_qty,
                    order.side.value, result.fill_price or 0.0, result.order_id
                )
            else:
                logger.warning(
                    "[epsilon.exec] Order %s: %s (id=%s, reason=%s)",
                    result.status, order.symbol, result.order_id, result.reason
                )

            self.store("last_order_result", result.model_dump(mode="json"))

            # Log trade to SessionLogger if available and order was filled
            if self._session_logger and result.status in ("FILLED", "PARTIAL"):
                self._session_logger.log_trade(
                    pod_id=self._pod_id,
                    order_info={
                        "order_id": result.order_id,
                        "symbol": order.symbol,
                        "side": order.side.value,
                        "qty": result.fill_qty,
                        "fill_price": result.fill_price,
                        "notional": result.fill_qty * (result.fill_price or 0.0),
                        "timestamp": (
                            result.filled_at.isoformat()
                            if result.filled_at
                            else datetime.now().isoformat()
                        ),
                        "status": result.status,
                    },
                )

            return {"order_executed": True, "execution_result": result.model_dump(mode="json")}

        except Exception as exc:
            logger.error("[epsilon.exec] Order execution failed: %s", exc)
            return {"order_executed": False, "execution_error": str(exc)}

    def _queue_for_paper_adapter(self, order: Order) -> dict:
        """Queue order for paper adapter (backtest mode)."""
        pending = self.recall("pending_orders", [])
        pending.append(order.model_dump(mode="json"))
        self.store("pending_orders", pending)
        return {"order_queued": True}
