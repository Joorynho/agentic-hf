from __future__ import annotations
import logging
from datetime import datetime, timezone
from src.core.models.enums import Side, OrderType
from src.core.models.execution import Order
from src.pods.base.agent import BasePodAgent

logger = logging.getLogger(__name__)
BASE_QTY = 100.0


class EpsilonPMAgent(BasePodAgent):
    """Rule-based regime classifier -> position in VXX/SVXY/SPY."""

    REGIME_MAP = {
        "low":     ("SVXY", Side.BUY,  BASE_QTY),          # short vol
        "normal":  (None,   None,      0.0),                # flat
        "high":    ("VXX",  Side.BUY,  BASE_QTY),           # long vol
        "extreme": ("VXX",  Side.BUY,  BASE_QTY * 1.5),     # max long vol
    }

    async def run_cycle(self, context: dict) -> dict:
        if context.get("risk_revision") and context.get("order"):
            return {"order": context["order"]}

        regime = context.get("regime", self.recall("regime", "normal"))
        prev_regime = self.recall("prev_regime", None)
        bar = context.get("bar")

        if regime == prev_regime:
            return {}  # No regime change -- no trade

        self.store("prev_regime", regime)
        symbol, side, qty = self.REGIME_MAP.get(regime, (None, None, 0.0))

        if symbol is None or qty == 0:
            return {}

        # Extreme regime: also add SPY hedge (sell SPY)
        orders = []
        order = Order(
            pod_id=self._pod_id, symbol=symbol, side=side,
            order_type=OrderType.MARKET, quantity=qty,
            limit_price=None, timestamp=datetime.now(timezone.utc),
            strategy_tag=f"vol_regime_{regime}",
        )
        orders.append(order)

        if regime == "extreme":
            spy_hedge = Order(
                pod_id=self._pod_id, symbol="SPY", side=Side.SELL,
                order_type=OrderType.MARKET, quantity=BASE_QTY * 0.5,
                limit_price=None, timestamp=datetime.now(timezone.utc),
                strategy_tag="vol_regime_extreme_hedge",
            )
            orders.append(spy_hedge)

        logger.info("[epsilon.pm] regime=%s -> %s %s %.0f", regime, side, symbol, qty)
        # Return first order (PodRuntime handles one order per cycle)
        return {"order": orders[0]}
