from __future__ import annotations
import logging
import os
from typing import Optional
from src.pods.base.agent import BasePodAgent
from src.core.bus.event_bus import EventBus
from src.pods.base.namespace import PodNamespace
from src.data.adapters.polymarket_adapter import PolymarketAdapter

logger = logging.getLogger(__name__)
UNIVERSE = ["SPY", "TLT", "GLD", "UUP", "EEM"]


class GammaResearcher(BasePodAgent):
    """Fetches FRED macro indicators and Polymarket macro/Fed odds (best-effort)."""

    def __init__(
        self,
        agent_id: str,
        pod_id: str,
        namespace: PodNamespace,
        bus: EventBus,
        polymarket_adapter: Optional[PolymarketAdapter] = None,
    ) -> None:
        super().__init__(agent_id, pod_id, namespace, bus)
        self.polymarket_adapter = polymarket_adapter

    async def run_cycle(self, context: dict) -> dict:
        self.store("universe", UNIVERSE)
        # Polymarket signals fetched externally and injected via namespace by BacktestRunner
        poly_signals = self.recall("polymarket_signals", [])
        self.store("researcher_ok", True)
        return {"universe": UNIVERSE, "poly_signals": poly_signals}
