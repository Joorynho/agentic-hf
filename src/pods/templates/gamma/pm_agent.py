from __future__ import annotations
import logging
from datetime import datetime, timezone
from src.core.llm import has_llm_key, llm_chat, extract_json
from src.core.models.enums import Side, OrderType
from src.core.models.execution import Order
from src.pods.base.agent import BasePodAgent

logger = logging.getLogger(__name__)

UNIVERSE = ["SPY", "TLT", "GLD", "UUP", "EEM"]
BASE_QTY = 50.0


class GammaPMAgent(BasePodAgent):
    """LLM-assisted macro PM. Falls back to momentum-ranked rule if no API key."""

    async def run_cycle(self, context: dict) -> dict:
        if context.get("risk_revision") and context.get("order"):
            return {"order": context["order"]}

        macro_score = context.get("macro_score", self.recall("macro_score", 0.0))
        bar = context.get("bar")
        if bar is None or macro_score == 0.0:
            return {}

        if has_llm_key():
            return await self._llm_decision(macro_score, bar)
        return self._rule_based_decision(macro_score, bar)

    def _rule_based_decision(self, macro_score: float, bar) -> dict:
        """Momentum-ranked: positive score -> buy SPY, negative -> buy TLT."""
        symbol = "SPY" if macro_score > 0 else "TLT"
        side = Side.BUY if macro_score > 0.01 else Side.SELL

        # Avoid re-entering same direction
        last_side = self.recall(f"last_side_{symbol}", None)
        if last_side == side.value:
            return {}

        order = Order(
            pod_id=self._pod_id,
            symbol=symbol,
            side=side,
            order_type=OrderType.MARKET,
            quantity=BASE_QTY,
            limit_price=None,
            timestamp=datetime.now(timezone.utc),
            strategy_tag=f"macro_momentum_{symbol}",
        )
        self.store(f"last_side_{symbol}", side.value)
        logger.info("[gamma.pm] rule-based: %s %s score=%.4f", side, symbol, macro_score)
        return {"order": order}

    async def _llm_decision(self, macro_score: float, bar) -> dict:
        try:
            prompt = (
                f"You are a macro PM. Macro score: {macro_score:.4f}. "
                f"Current price: {bar.close}. "
                "Choose one: BUY SPY, BUY TLT, BUY GLD, or HOLD. Reply with JSON only: "
                '{"action": "BUY"|"HOLD", "symbol": "SPY"|"TLT"|"GLD"|"UUP"|"EEM", "rationale": "..."}'
            )
            raw = llm_chat([{"role": "user", "content": prompt}], max_tokens=200)
            decision = extract_json(raw)
            if decision.get("action") == "HOLD":
                return {}
            symbol = decision.get("symbol", "SPY")
            order = Order(
                pod_id=self._pod_id,
                symbol=symbol,
                side=Side.BUY,
                order_type=OrderType.MARKET,
                quantity=BASE_QTY,
                limit_price=None,
                timestamp=datetime.now(timezone.utc),
                strategy_tag=f"macro_llm_{symbol}",
            )
            logger.info("[gamma.pm] LLM: %s rationale=%s", symbol, decision.get("rationale", ""))
            return {"order": order}
        except Exception as exc:
            logger.info("[gamma.pm] LLM failed (%s) — fallback to rule-based", exc)
            return self._rule_based_decision(macro_score, bar)
