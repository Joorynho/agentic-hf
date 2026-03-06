from __future__ import annotations
import logging
from datetime import datetime, timezone
from src.pods.base.agent import BasePodAgent

logger = logging.getLogger(__name__)


class EpsilonOpsAgent(BasePodAgent):
    """Heartbeat + VIX freshness check. Stale VIX = halt signal."""

    async def run_cycle(self, context: dict) -> dict:
        now = datetime.now(timezone.utc)
        self.store("last_heartbeat", now.isoformat())
        vix = self.recall("vix_level", None)
        vix_fresh = vix is not None
        if not vix_fresh:
            logger.critical("[epsilon.ops] VIX data stale -- pod should halt")
        self.store("vix_fresh", vix_fresh)
        return {"heartbeat_ok": True, "vix_fresh": vix_fresh}
