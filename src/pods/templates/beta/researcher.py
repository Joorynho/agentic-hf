from __future__ import annotations
import logging
from src.pods.base.agent import BasePodAgent

logger = logging.getLogger(__name__)

PAIRS = [("XLK", "XLF"), ("XLE", "XLV"), ("XLI", "XLY"), ("XLP", "XLU")]


class BetaResearcher(BasePodAgent):
    """Stores pair universe and updates sector momentum signals."""

    async def run_cycle(self, context: dict) -> dict:
        # Store pair universe so signal agent can retrieve it
        self.store("pairs", PAIRS)
        self.store("researcher_ok", True)
        return {"pairs": PAIRS}
