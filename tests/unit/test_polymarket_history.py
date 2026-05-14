from datetime import datetime, timezone

from src.core.models.polymarket import PolymarketSignal
from src.data.adapters.market_tracker import MarketTracker


def _signal(market_id: str, prob: float, volume: float = 1000.0) -> PolymarketSignal:
    return PolymarketSignal(
        market_id=market_id,
        question=f"Will {market_id} happen?",
        yes_price=prob,
        no_price=1.0 - prob,
        implied_prob=prob,
        spread=0.02,
        volume_24h=volume,
        open_interest=volume * 2,
        timestamp=datetime.now(timezone.utc),
        tags=["macro"],
    )


def test_market_tracker_exposes_price_history_for_dashboard() -> None:
    tracker = MarketTracker(max_markets=10)

    first = tracker.update([_signal("oil-risk", 0.42)])
    second = tracker.update([_signal("oil-risk", 0.48)])

    assert first[0]["price_history"][0]["implied_prob"] == 0.42
    history = second[0]["price_history"]
    assert len(history) == 2
    assert [point["implied_prob"] for point in history] == [0.42, 0.48]
    assert all(point["ts"] for point in history)
