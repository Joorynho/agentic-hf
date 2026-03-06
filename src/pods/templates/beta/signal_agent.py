from __future__ import annotations
import logging
import math
from src.pods.base.agent import BasePodAgent

logger = logging.getLogger(__name__)

WINDOW = 60  # rolling z-score window in bars


class BetaSignalAgent(BasePodAgent):
    """Computes rolling z-score of log price ratio for each ETF pair."""

    async def run_cycle(self, context: dict) -> dict:
        bar = context.get("bar")
        if bar is None:
            return {}

        pairs = context.get("pairs", self.recall("pairs", []))
        signals = {}

        for leg_a, leg_b in pairs:
            key = f"ratio_history_{leg_a}_{leg_b}"
            history: list[float] = self.recall(key, [])

            # Use bar.close as proxy; in real impl each symbol would have its own bar.
            # For MVP: use a deterministic noise-free synthetic ratio based on symbol hash.
            price_a = bar.close * (1.0 + hash(leg_a) % 10 * 0.01)
            price_b = bar.close * (1.0 + hash(leg_b) % 10 * 0.01)
            ratio = math.log(price_a / price_b)

            history.append(ratio)
            if len(history) > WINDOW:
                history = history[-WINDOW:]
            self.store(key, history)

            if len(history) >= 5:
                mean = sum(history) / len(history)
                variance = sum((x - mean) ** 2 for x in history) / len(history)
                std = math.sqrt(variance) if variance > 0 else 1e-8
                z = (ratio - mean) / std
            else:
                z = 0.0

            pair_key = f"{leg_a}_{leg_b}"
            signals[pair_key] = round(z, 4)
            self.store(f"zscore_{pair_key}", z)

        self.store("latest_signals", signals)
        logger.debug("[beta.signal] z-scores: %s", signals)
        return {"signals": signals}
