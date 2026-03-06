from __future__ import annotations
import logging
from src.pods.base.agent import BasePodAgent

logger = logging.getLogger(__name__)

# VIX regime thresholds
LOW    = 15.0
NORMAL = 25.0
HIGH   = 35.0

class EpsilonSignalAgent(BasePodAgent):
    """Classifies VIX regime: Low / Normal / High / Extreme."""

    async def run_cycle(self, context: dict) -> dict:
        vix = context.get("vix_level", self.recall("vix_level", 20.0))
        ratio = context.get("front_back_ratio", self.recall("front_back_ratio", 1.0))

        if vix < LOW:
            regime = "low"
        elif vix < NORMAL:
            regime = "normal"
        elif vix < HIGH:
            regime = "high"
        else:
            regime = "extreme"

        self.store("regime", regime)
        self.store("vix_level", vix)
        logger.debug("[epsilon.signal] VIX=%.1f regime=%s ratio=%.3f", vix, regime, ratio)
        return {"regime": regime, "vix_level": vix, "front_back_ratio": ratio}
