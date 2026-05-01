"""Capital allocator max_pct ceiling."""

from src.backtest.accounting.capital_allocator import CapitalAllocator
from src.core.bus.event_bus import EventBus


def test_suggest_reallocation_max_pct_40():
    bus = EventBus()
    ca = CapitalAllocator(pod_ids=["a", "b", "c", "d"], bus=bus)
    scores = {"a": 0.9, "b": 0.8, "c": 0.7, "d": 0.6}
    out = ca.suggest_reallocation(scores, min_pct=0.15, max_pct=0.40)
    assert abs(sum(out.values()) - 1.0) < 0.01
    for v in out.values():
        assert v <= 0.40 + 0.001
        assert v >= 0.15 - 0.001
