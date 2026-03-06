from __future__ import annotations
import logging
from src.pods.base.agent import BasePodAgent

logger = logging.getLogger(__name__)
UNIVERSE = ["AAPL", "MSFT", "AMZN", "GOOGL", "META"]

class DeltaResearcher(BasePodAgent):
    """GDELT event scoring + EDGAR 8-K freshness (synthetic in backtest)."""

    async def run_cycle(self, context: dict) -> dict:
        self.store("universe", UNIVERSE)
        # In backtest: synthetic event score based on bar index (deterministic)
        bar = context.get("bar")
        event_score = 0.0
        if bar is not None:
            # Deterministic synthetic: high score every ~20 bars
            bar_ts = int(bar.timestamp.timestamp()) % 100
            event_score = 0.8 if bar_ts < 5 else 0.3
        self.store("event_score", event_score)
        self.store("researcher_ok", True)
        return {"event_score": event_score, "universe": UNIVERSE}
