from __future__ import annotations
import logging
from src.pods.base.agent import BasePodAgent

logger = logging.getLogger(__name__)
FAST = 20
SLOW = 60


class GammaSignalAgent(BasePodAgent):
    """Cross-asset momentum signal + synthetic yield curve slope."""

    async def run_cycle(self, context: dict) -> dict:
        bar = context.get("bar")
        if bar is None:
            return {}

        # Rolling momentum per asset (stored per symbol in namespace)
        symbol = bar.symbol if hasattr(bar, "symbol") else "SPY"
        history_key = f"price_history_{symbol}"
        history: list[float] = self.recall(history_key, [])
        history.append(bar.close)
        if len(history) > SLOW:
            history = history[-SLOW:]
        self.store(history_key, history)

        fast_mom = 0.0
        slow_mom = 0.0
        if len(history) >= FAST:
            fast_mom = (history[-1] - history[-FAST]) / history[-FAST]
        if len(history) >= SLOW:
            slow_mom = (history[-1] - history[-SLOW]) / history[-SLOW]

        # Synthetic yield curve slope: use bar close modulo to simulate
        yield_curve_slope = 0.5 + (bar.close % 10) * 0.01

        macro_score = (fast_mom * 0.6 + slow_mom * 0.4) * (1 + yield_curve_slope)
        self.store("macro_score", macro_score)
        self.store("yield_curve_slope", yield_curve_slope)
        logger.debug("[gamma.signal] macro_score=%.4f", macro_score)
        return {"macro_score": macro_score, "yield_curve_slope": yield_curve_slope}
