from __future__ import annotations
import logging
from datetime import datetime, timezone
from src.core.models.enums import Side, OrderType
from src.core.models.execution import Order
from src.pods.base.agent import BasePodAgent

logger = logging.getLogger(__name__)

ENTRY_Z = 2.0
EXIT_Z = 0.5
STOP_Z = 3.5
BASE_QUANTITY = 100.0


class BetaPMAgent(BasePodAgent):
    """Rule-based pairs PM: enter when |z|>2, exit when |z|<0.5, stop-loss at |z|>3.5."""

    async def run_cycle(self, context: dict) -> dict:
        # If this is a risk-revision cycle, accept the revised order and pass it through
        if context.get("risk_revision") and context.get("order"):
            return {"order": context["order"]}

        signals: dict = context.get("signals", self.recall("latest_signals", {}))
        if not signals:
            return {}

        # Pick the pair with the highest absolute z-score
        best_pair = max(signals, key=lambda k: abs(signals[k]))
        z = signals[best_pair]
        leg_a, leg_b = best_pair.split("_")

        position_key = f"position_{best_pair}"
        current_pos = self.recall(position_key, 0.0)  # +1 long, -1 short, 0 flat

        bar = context.get("bar")
        price = bar.close if bar else 100.0  # noqa: F841  kept for future slippage calc
        now = datetime.now(timezone.utc)

        order = None

        if abs(z) > STOP_Z and current_pos != 0:
            # Stop-loss: close position
            side = Side.SELL if current_pos > 0 else Side.BUY
            order = Order(
                pod_id=self._pod_id, symbol=leg_a, side=side,
                order_type=OrderType.MARKET, quantity=BASE_QUANTITY,
                limit_price=None, timestamp=now,
                strategy_tag=f"stop_{best_pair}",
            )
            self.store(position_key, 0.0)

        elif abs(z) > ENTRY_Z and current_pos == 0:
            # Entry: buy the underperformer (negative z => leg_a lagged => buy leg_a)
            side = Side.BUY if z < 0 else Side.SELL
            order = Order(
                pod_id=self._pod_id, symbol=leg_a, side=side,
                order_type=OrderType.MARKET, quantity=BASE_QUANTITY,
                limit_price=None, timestamp=now,
                strategy_tag=f"entry_{best_pair}",
            )
            self.store(position_key, 1.0 if side == Side.BUY else -1.0)

        elif abs(z) < EXIT_Z and current_pos != 0:
            # Exit: mean reversion achieved
            side = Side.SELL if current_pos > 0 else Side.BUY
            order = Order(
                pod_id=self._pod_id, symbol=leg_a, side=side,
                order_type=OrderType.MARKET, quantity=BASE_QUANTITY,
                limit_price=None, timestamp=now,
                strategy_tag=f"exit_{best_pair}",
            )
            self.store(position_key, 0.0)

        if order:
            logger.info(
                "[beta.pm] %s z=%.2f order=%s qty=%.0f",
                best_pair, z, order.side, order.quantity,
            )

        return {"order": order}
