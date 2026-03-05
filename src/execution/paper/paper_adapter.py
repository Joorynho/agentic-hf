from __future__ import annotations

import math
from datetime import datetime

from src.execution.base.adapter import ExecutionAdapter
from src.core.models.execution import Order, Fill, RejectedOrder, RiskApprovalToken
from src.core.models.market import Bar
from src.core.models.enums import Side


class PaperAdapter(ExecutionAdapter):
    def __init__(self, tcm_bps: float = 5.0, slippage_model: str = "fixed"):
        self._tcm_bps = tcm_bps
        self._slippage_model = slippage_model

    async def execute(
        self, order: Order, token: RiskApprovalToken, current_bar: Bar
    ) -> Fill | RejectedOrder:
        if not token.is_valid():
            return RejectedOrder(order_id=order.id, reason="risk approval token expired")
        if token.pod_id != order.pod_id:
            return RejectedOrder(order_id=order.id, reason="token pod_id mismatch")

        fill_price = self._compute_fill_price(order, current_bar)
        commission = fill_price * order.quantity * self._tcm_bps / 10_000

        return Fill(
            order_id=order.id,
            pod_id=order.pod_id,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=fill_price,
            commission=commission,
            timestamp=datetime.now(),
        )

    def _compute_fill_price(self, order: Order, bar: Bar) -> float:
        base = bar.close
        slip_factor = self._tcm_bps / 10_000
        if self._slippage_model == "sqrt_impact":
            slip_factor *= math.sqrt(order.quantity / max(bar.volume, 1))
        direction = 1.0 if order.side == Side.BUY else -1.0
        return base * (1 + direction * slip_factor)
