from __future__ import annotations
import logging
from datetime import datetime, timezone
from src.core.llm import has_llm_key, llm_chat, extract_json
from src.core.models.enums import Side, OrderType
from src.core.models.execution import Order
from src.pods.base.agent import BasePodAgent

logger = logging.getLogger(__name__)
_HAS_LLM = has_llm_key()
BASE_QTY = 50.0
SIGNAL_THRESHOLD = 0.5
MAX_HOLD_BARS = 5


class DeltaPMAgent(BasePodAgent):
    """LLM-assisted event PM with 5-day auto-expiry. Falls back to threshold rule."""

    async def run_cycle(self, context: dict) -> dict:
        if context.get("risk_revision") and context.get("order"):
            return {"order": context["order"]}

        composite = context.get("composite_score", self.recall("composite_score", 0.0))
        bar = context.get("bar")
        if bar is None:
            return {}

        # Auto-expiry: close positions after MAX_HOLD_BARS
        hold_bars = self.recall("hold_bars", 0)
        active = self.recall("active_position", False)
        if active:
            hold_bars += 1
            self.store("hold_bars", hold_bars)
            if hold_bars >= MAX_HOLD_BARS:
                self.store("active_position", False)
                self.store("hold_bars", 0)
                order = Order(
                    pod_id=self._pod_id, symbol="AAPL", side=Side.SELL,
                    order_type=OrderType.MARKET, quantity=BASE_QTY,
                    limit_price=None, timestamp=datetime.now(timezone.utc),
                    strategy_tag="delta_auto_expiry",
                )
                logger.info("[delta.pm] Auto-expiry close after %d bars", hold_bars)
                return {"order": order}
            return {}

        if composite < SIGNAL_THRESHOLD:
            return {}

        if _HAS_LLM:
            return await self._llm_decision(composite, bar)
        return self._rule_based_decision(composite, bar)

    def _rule_based_decision(self, composite: float, bar) -> dict:
        self.store("active_position", True)
        self.store("hold_bars", 0)
        order = Order(
            pod_id=self._pod_id, symbol="AAPL", side=Side.BUY,
            order_type=OrderType.MARKET, quantity=BASE_QTY,
            limit_price=None, timestamp=datetime.now(timezone.utc),
            strategy_tag=f"delta_event_{composite:.2f}",
        )
        logger.info("[delta.pm] rule-based entry: composite=%.3f", composite)
        return {"order": order}

    async def _llm_decision(self, composite: float, bar) -> dict:
        try:
            prompt = (
                f"Event-driven PM. Composite signal: {composite:.3f}. Price: {bar.close}. "
                "Reply with JSON only: {\"action\": \"BUY\"|\"HOLD\", \"symbol\": \"AAPL\", \"rationale\": \"...\"}"
            )
            raw = llm_chat([{"role": "user", "content": prompt}], max_tokens=150)
            decision = extract_json(raw)
            if decision.get("action") == "HOLD":
                return {}
            self.store("active_position", True)
            self.store("hold_bars", 0)
            order = Order(
                pod_id=self._pod_id, symbol=decision.get("symbol", "AAPL"),
                side=Side.BUY, order_type=OrderType.MARKET, quantity=BASE_QTY,
                limit_price=None, timestamp=datetime.now(timezone.utc),
                strategy_tag=f"delta_llm_{composite:.2f}",
            )
            return {"order": order}
        except Exception as exc:
            logger.info("[delta.pm] LLM failed (%s) — fallback", exc)
            return self._rule_based_decision(composite, bar)
