from __future__ import annotations
import statistics
from src.pods.base.namespace import PodNamespace
from src.core.models.market import Bar

class MomentumPMAgent:
    """Rule-based momentum PM: fast MA vs slow MA crossover signal."""

    def __init__(self, pod_id: str, namespace: PodNamespace,
                 fast_window: int = 10, slow_window: int = 30):
        self._pod_id = pod_id
        self._ns = namespace
        self._fast = fast_window
        self._slow = slow_window

    def compute_signal(self, symbol: str, bars: list[Bar]) -> float:
        if len(bars) < self._slow:
            return 0.0
        closes = [b.close for b in bars]
        fast_ma = statistics.mean(closes[-self._fast:])
        slow_ma = statistics.mean(closes[-self._slow:])
        signal = (fast_ma - slow_ma) / slow_ma
        self._ns.set(f"signal::{symbol}", signal)
        return signal
