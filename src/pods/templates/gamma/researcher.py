from __future__ import annotations
import logging
import os
from src.pods.base.agent import BasePodAgent

logger = logging.getLogger(__name__)
UNIVERSE = ["SPY", "TLT", "GLD", "UUP", "EEM"]


class GammaResearcher(BasePodAgent):
    """Fetches FRED macro indicators and Polymarket macro/Fed odds (best-effort)."""

    async def run_cycle(self, context: dict) -> dict:
        self.store("universe", UNIVERSE)
        # Polymarket signals fetched externally and injected via namespace by BacktestRunner
        poly_signals = self.recall("polymarket_signals", [])
        self.store("researcher_ok", True)
        return {"universe": UNIVERSE, "poly_signals": poly_signals}
