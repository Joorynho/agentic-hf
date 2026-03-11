from __future__ import annotations

import logging
from typing import Optional

from src.core.bus.event_bus import EventBus
from src.data.adapters.fred_adapter import FredAdapter
from src.pods.base.agent import BasePodAgent
from src.pods.base.namespace import PodNamespace

logger = logging.getLogger(__name__)


class EpsilonResearcher(BasePodAgent):
    """Fetches VIX term structure + FRED credit spreads.

    When a FredAdapter is provided, uses real VIXCLS, credit spread
    (BAMLH0A0HYM2), and yield curve slope (T10Y2Y). Falls back to
    synthetic values derived from bar close in backtest mode.
    """

    def __init__(
        self,
        agent_id: str,
        pod_id: str,
        namespace: PodNamespace,
        bus: EventBus,
        fred_adapter: Optional[FredAdapter] = None,
    ) -> None:
        super().__init__(agent_id, pod_id, namespace, bus)
        self.fred_adapter = fred_adapter

    async def run_cycle(self, context: dict) -> dict:
        if self.fred_adapter:
            snapshot = await self.fred_adapter.fetch_snapshot()
            if snapshot:
                return self._from_fred(snapshot)

        return self._synthetic(context)

    def _from_fred(self, snapshot: dict[str, float]) -> dict:
        vix_level = FredAdapter.extract(snapshot, "VIXCLS", 20.0)
        credit_spread = FredAdapter.extract(snapshot, "BAMLH0A0HYM2", 4.0)
        yield_slope = FredAdapter.extract(snapshot, "T10Y2Y", 0.0)
        fed_rate = FredAdapter.extract(snapshot, "DFF", 5.0)

        # VIX-based front/back ratio estimate: inverted VIX ≥30 → contango
        front_back_ratio = 0.90 + max(0.0, (30.0 - vix_level)) * 0.005
        front_back_ratio = round(min(1.1, max(0.80, front_back_ratio)), 4)

        self.store("vix_level", vix_level)
        self.store("front_back_ratio", front_back_ratio)
        self.store("credit_spread", credit_spread)
        self.store("yield_slope", yield_slope)
        self.store("fed_rate", fed_rate)
        self.store("fred_snapshot", snapshot)
        self.store("researcher_ok", True)

        logger.info(
            "[epsilon.researcher] FRED: VIX=%.1f credit=%.2f slope=%.2f",
            vix_level, credit_spread, yield_slope,
        )
        return {"vix_level": vix_level, "front_back_ratio": front_back_ratio}

    def _synthetic(self, context: dict) -> dict:
        """Deterministic synthetic values for backtest mode."""
        bar = context.get("bar")
        vix_level = 20.0 * (100.0 / bar.close) if bar and bar.close > 0 else 20.0
        front_back_ratio = 0.95 + (vix_level % 5) * 0.01

        self.store("vix_level", vix_level)
        self.store("front_back_ratio", front_back_ratio)
        self.store("researcher_ok", True)
        return {"vix_level": vix_level, "front_back_ratio": front_back_ratio}
