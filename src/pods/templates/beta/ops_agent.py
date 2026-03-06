from __future__ import annotations
import logging
from datetime import datetime, timezone
from src.pods.base.agent import BasePodAgent

logger = logging.getLogger(__name__)

_KNOWN_POSITION_KEYS = [
    "position_XLK_XLF",
    "position_XLE_XLV",
    "position_XLI_XLY",
    "position_XLP_XLU",
]


class BetaOpsAgent(BasePodAgent):
    """Heartbeat + pair leg reconciliation."""

    async def run_cycle(self, context: dict) -> dict:
        now = datetime.now(timezone.utc)
        self.store("last_heartbeat", now.isoformat())

        # Reconcile: every known position key should map to a valid pair
        pairs = self.recall("pairs", [])
        pair_keys = {f"{a}_{b}" for a, b in pairs}
        for key in _KNOWN_POSITION_KEYS:
            pair = key.replace("position_", "")
            if pairs and pair not in pair_keys:
                logger.warning("[beta.ops] Unrecognised position key: %s", key)

        return {"heartbeat_ok": True, "ts": now.isoformat()}
