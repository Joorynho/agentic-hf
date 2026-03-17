from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Optional

from src.core.models.allocation import MandateUpdate
from src.core.models.enums import Side
from src.core.models.execution import Order, RiskApprovalToken, OrderResult
from src.core.models.messages import AgentMessage
from src.execution.paper.alpaca_adapter import AlpacaAdapter
from src.pods.base.agent import BasePodAgent

logger = logging.getLogger(__name__)


class EquitiesExecutionTrader(BasePodAgent):
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
            logger.warning(
                "[equities.exec] Invalid/expired token — order %s rejected", order.id
            )
            return {"execution_rejected": True}

        # Extract governance state from context (passed by SessionManager)
        mandate: Optional[MandateUpdate] = context.get("mandate")
        risk_halt: bool = context.get("risk_halt", False)

        # Check risk halt first (hard constraint)
        if risk_halt:
            risk_halt_reason = context.get("risk_halt_reason", "Unknown risk constraint breach")
            logger.error(
                "[equities.exec] Order %s rejected: Risk halt active (%s)", order.id, risk_halt_reason
            )
            self._session_logger and self._session_logger.log_reasoning(
                f"execution:{self._pod_id}",
                "order_rejected_risk_halt",
                f"Order {order.symbol} rejected due to risk halt: {risk_halt_reason}",
            )
            return {
                "execution_rejected": True,
                "rejection_reason": "risk_halt_active",
                "rejection_detail": risk_halt_reason,
            }

        # If Alpaca adapter is available, execute via Alpaca; otherwise queue for paper adapter
        if self._alpaca:
            return await self._execute_via_alpaca(order, token, mandate=mandate)
        else:
            return self._queue_for_paper_adapter(order)

    async def _execute_via_alpaca(
        self, order: Order, token: RiskApprovalToken, mandate: Optional[MandateUpdate] = None
    ) -> dict:
        """Execute order via Alpaca API, respecting CIO allocation and CRO risk constraints."""
        try:
            # Check allocation constraint (from CIO mandate)
            if mandate and self._pod_id in mandate.pod_allocations:
                allocation_pct = mandate.pod_allocations[self._pod_id]
                firm_nav = mandate.firm_nav if mandate.firm_nav > 0 else 1.0

                # Calculate current notional and requested notional
                current_positions = self.recall("current_positions", {})
                last_prices = self.recall("last_prices", {})
                current_notional = sum(
                    pos.get("qty", 0) * last_prices.get(pos.get("symbol", ""), 100)
                    for pos in (current_positions.values() if isinstance(current_positions, dict) else [])
                )

                last_price = last_prices.get(order.symbol, 100.0)
                requested_notional = order.quantity * last_price
                max_notional = allocation_pct * firm_nav

                # If exceeds allocation, try to scale order down
                if current_notional + requested_notional > max_notional:
                    available_notional = max_notional - current_notional
                    if available_notional <= 0:
                        logger.warning(
                            "[equities.exec] Order %s rejected: allocation limit reached (%.0f%%, current=$%.2f, max=$%.2f)",
                            order.id, allocation_pct * 100, current_notional, max_notional,
                        )
                        self._session_logger and self._session_logger.log_reasoning(
                            f"execution:{self._pod_id}",
                            "order_rejected_allocation_limit",
                            f"Order {order.symbol} rejected: allocation limit reached ({allocation_pct*100:.0f}%)",
                        )
                        return {
                            "execution_rejected": True,
                            "rejection_reason": "allocation_limit_exceeded",
                            "rejection_detail": f"Allocation {allocation_pct*100:.0f}% limit reached",
                        }

                    # Scale order down to fit allocation
                    scaled_qty = available_notional / last_price
                    logger.info(
                        "[equities.exec] Scaling order %s from %.2f to %.2f (allocation limit)",
                        order.id, order.quantity, scaled_qty,
                    )
                    self._session_logger and self._session_logger.log_reasoning(
                        f"execution:{self._pod_id}",
                        "order_scaled_allocation",
                        f"Order {order.symbol} scaled from {order.quantity} to {scaled_qty} shares",
                    )
                    # Mutate the order quantity
                    order.quantity = scaled_qty

            # Check leverage limit from risk token
            if token and hasattr(token, "constraints") and token.constraints:
                max_leverage = token.constraints.get("max_leverage", 2.0)
                current_positions = self.recall("current_positions", {})
                last_prices = self.recall("last_prices", {})
                current_nav = self.recall("current_nav", 10000.0)  # Default to $10k

                current_notional = sum(
                    pos.get("qty", 0) * last_prices.get(pos.get("symbol", ""), 100)
                    for pos in (current_positions.values() if isinstance(current_positions, dict) else [])
                )
                last_price = last_prices.get(order.symbol, 100.0)
                requested_notional = order.quantity * last_price
                new_leverage = (current_notional + requested_notional) / current_nav if current_nav > 0 else 0

                if new_leverage > max_leverage:
                    logger.warning(
                        "[equities.exec] Order %s rejected: leverage limit (%.1fx) exceeded (current+requested=%.1fx)",
                        order.id, max_leverage, new_leverage,
                    )
                    self._session_logger and self._session_logger.log_reasoning(
                        f"execution:{self._pod_id}",
                        "order_rejected_leverage_limit",
                        f"Order {order.symbol} rejected: leverage {new_leverage:.1f}x exceeds limit {max_leverage:.1f}x",
                    )
                    return {
                        "execution_rejected": True,
                        "rejection_reason": "leverage_limit_exceeded",
                        "rejection_detail": f"Leverage {new_leverage:.1f}x exceeds {max_leverage:.1f}x limit",
                    }

        except Exception as e:
            logger.error("[equities.exec] Error checking governance constraints: %s", e)
            # Continue with execution (fail-open for allocation checks)

        try:
            logger.info(
                "[equities.exec] Submitting order to Alpaca: %s %.0f %s @ $%s",
                order.side.value, order.quantity, order.symbol, order.limit_price or "MARKET"
            )

            await self._broadcast_order_update(
                order, status="PENDING", fill_price=None, fill_qty=0.0,
            )

            # Call Alpaca to place order
            result_dict = await self._alpaca.place_order(
                symbol=order.symbol,
                qty=order.quantity,
                side=order.side.value,
                order_type="limit" if order.order_type.value == "limit" else "market",
                limit_price=order.limit_price,
            )

            # Convert result to OrderResult model
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

            # Log execution result
            if result.status in ("FILLED", "PARTIAL"):
                logger.info(
                    "[equities.exec] Order %s: %s %.0f %s @ $%.2f (id=%s)",
                    result.status, order.symbol, result.fill_qty,
                    order.side.value, result.fill_price or 0.0, result.order_id
                )
            else:
                logger.warning(
                    "[equities.exec] Order %s: %s (id=%s, reason=%s)",
                    result.status, order.symbol, result.order_id, result.reason
                )

            await self._broadcast_order_update(
                order, status=result.status,
                fill_price=result.fill_price, fill_qty=result.fill_qty,
                order_id=result.order_id, reason=result.reason,
            )

            # Store result in namespace for ops agent
            self.store("last_order_result", result.model_dump(mode="json"))

            # Sync fill with PortfolioAccountant + publish to EventBus
            if result.status in ("FILLED", "PARTIAL"):
                accountant = self._ns.get("accountant")
                if accountant:
                    signed_qty = result.fill_qty if order.side == Side.BUY else -result.fill_qty
                    pm_meta = self._ns.get("pm_trade_metadata") or {}
                    accountant.record_fill_direct(
                        order_id=result.order_id or "",
                        symbol=order.symbol,
                        qty=signed_qty,
                        fill_price=result.fill_price or 0.0,
                        filled_at=result.filled_at,
                        reasoning=pm_meta.get("reasoning", ""),
                        strategy_tag=pm_meta.get("strategy_tag", order.strategy_tag),
                        signal_snapshot=pm_meta.get("signal_snapshot"),
                        conviction=pm_meta.get("conviction", order.conviction),
                        stop_loss_pct=pm_meta.get("stop_loss_pct"),
                        take_profit_pct=pm_meta.get("take_profit_pct"),
                        exit_when=pm_meta.get("exit_when", ""),
                        max_hold_days=pm_meta.get("max_hold_days", 0),
                    )

                try:
                    fill_msg = AgentMessage(
                        timestamp=datetime.now(timezone.utc),
                        sender=f"pod.{self._pod_id}.exec",
                        recipient="broadcast",
                        topic="execution.fill",
                        payload={
                            "pod_id": self._pod_id,
                            "order_id": result.order_id,
                            "symbol": order.symbol,
                            "side": order.side.value,
                            "qty": result.fill_qty,
                            "fill_price": result.fill_price,
                            "status": result.status,
                            "filled_at": result.filled_at.isoformat() if result.filled_at else None,
                        },
                    )
                    await self._bus.publish("execution.fill", fill_msg, publisher_id=f"pod.{self._pod_id}")
                except Exception as e:
                    logger.debug("[equities.exec] Failed to publish fill event: %s", e)

            # Log trade to SessionLogger if available and order was filled
            if self._session_logger and result.status in ("FILLED", "PARTIAL"):
                pm_meta = self._ns.get("pm_trade_metadata") or {}
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
                        "reasoning": pm_meta.get("reasoning", ""),
                        "conviction": pm_meta.get("conviction", 0.5),
                        "strategy_tag": pm_meta.get("strategy_tag", ""),
                    },
                )

            # Log mandate application if available
            if self._session_logger and mandate:
                allocation_pct = mandate.pod_allocations.get(self._pod_id, 0.0)
                self._session_logger.log_reasoning(
                    f"execution:{self._pod_id}",
                    "mandate_applied",
                    f"Order {order.symbol} {order.quantity}: Allocation {allocation_pct*100:.0f}%, "
                    f"Result: {result.status}",
                )

            # Publish agent activity for live intelligence feed
            try:
                action = "order_executed" if result.status in ("FILLED", "PARTIAL") else "order_rejected"
                summary = f"{order.side.value.upper()} {order.quantity:.0f} {order.symbol} → {result.status}"
                act_msg = AgentMessage(
                    timestamp=datetime.now(timezone.utc),
                    sender=f"pod.{self._pod_id}.exec",
                    recipient="dashboard",
                    topic="agent.activity",
                    payload={
                        "agent_id": f"{self._pod_id}_trader",
                        "agent_role": "Trader",
                        "pod_id": self._pod_id,
                        "action": action,
                        "summary": summary[:500],
                        "detail": f"Price: ${result.fill_price or 0:.2f}",
                    },
                )
                await self._bus.publish("agent.activity", act_msg, publisher_id=f"pod.{self._pod_id}")
            except Exception:
                pass

            return {"order_executed": True, "execution_result": result.model_dump(mode="json")}

        except Exception as exc:
            logger.error("[equities.exec] Order execution failed: %s", exc)
            return {
                "order_executed": False,
                "execution_error": str(exc),
            }

    async def _broadcast_order_update(
        self, order: Order, status: str,
        fill_price: float | None = None, fill_qty: float = 0.0,
        order_id: str | None = None, reason: str | None = None,
    ) -> None:
        """Publish order lifecycle event to EventBus for dashboard visibility."""
        try:
            msg = AgentMessage(
                timestamp=datetime.now(timezone.utc),
                sender=f"pod.{self._pod_id}.exec",
                recipient="broadcast",
                topic="execution.order_update",
                payload={
                    "pod_id": self._pod_id,
                    "order_id": order_id or str(order.id),
                    "symbol": order.symbol,
                    "side": order.side.value,
                    "qty": order.quantity,
                    "status": status,
                    "fill_price": fill_price,
                    "fill_qty": fill_qty,
                    "reason": reason,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
            await self._bus.publish("execution.order_update", msg, publisher_id=f"pod.{self._pod_id}")
        except Exception:
            pass

    def _queue_for_paper_adapter(self, order: Order) -> dict:
        """Queue order for paper adapter (backtest mode)."""
        pending = self.recall("pending_orders", [])
        pending.append(order.model_dump(mode="json"))
        self.store("pending_orders", pending)
        logger.info(
            "[equities.exec] Order queued (paper mode): %s %.0f %s",
            order.side.value, order.quantity, order.symbol,
        )
        return {"order_queued": True}
