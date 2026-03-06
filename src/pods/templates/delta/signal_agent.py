from __future__ import annotations
import logging
from src.pods.base.agent import BasePodAgent

logger = logging.getLogger(__name__)
EVENT_THRESHOLD = 0.7

class DeltaSignalAgent(BasePodAgent):
    """Combines GDELT event score * EDGAR freshness * proximity decay."""

    async def run_cycle(self, context: dict) -> dict:
        event_score = context.get("event_score", self.recall("event_score", 0.0))
        bar = context.get("bar")

        # Proximity decay: score degrades if we're far from event
        bars_since_event = self.recall("bars_since_event", 999)
        if event_score >= EVENT_THRESHOLD:
            bars_since_event = 0
        else:
            bars_since_event += 1
        self.store("bars_since_event", bars_since_event)

        decay = max(0.0, 1.0 - bars_since_event * 0.2)  # drops to 0 after 5 bars
        composite_score = event_score * decay
        self.store("composite_score", composite_score)
        logger.debug("[delta.signal] composite=%.3f event=%.3f decay=%.3f",
                     composite_score, event_score, decay)
        return {"composite_score": composite_score}
