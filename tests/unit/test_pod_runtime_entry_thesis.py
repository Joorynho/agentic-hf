from datetime import datetime, timezone

from src.core.models.enums import OrderType, Side
from src.core.models.execution import Order
from src.pods.runtime.pod_runtime import PodRuntime


def _order(symbol: str = "GLD") -> Order:
    return Order(
        pod_id="commodities",
        symbol=symbol,
        side=Side.BUY,
        order_type=OrderType.MARKET,
        quantity=1.0,
        timestamp=datetime(2026, 4, 29, tzinfo=timezone.utc),
        strategy_tag="llm_pm",
        conviction=0.8,
    )


def test_entry_thesis_prefers_matching_trade_reasoning():
    runtime = PodRuntime.__new__(PodRuntime)

    thesis = runtime._entry_thesis_for_order(
        _order("GLD"),
        {"symbol": "GLD", "reasoning": "THESIS: gold breakout confirmed"},
        {"reasoning": "raw response"},
    )

    assert thesis == "THESIS: gold breakout confirmed"


def test_entry_thesis_unwraps_raw_pm_json_payload():
    runtime = PodRuntime.__new__(PodRuntime)
    raw_payload = (
        '{"trades": ['
        '{"action": "BUY", "symbol": "GDX", "qty": 1, '
        '"reasoning": "THESIS: miners have operating leverage to gold"}'
        ']}'
    )

    thesis = runtime._entry_thesis_for_order(_order("GDX"), {}, {"reasoning": raw_payload})

    assert thesis == "THESIS: miners have operating leverage to gold"


def test_entry_thesis_does_not_use_unmatched_raw_json_blob():
    runtime = PodRuntime.__new__(PodRuntime)
    raw_payload = (
        '{"trades": ['
        '{"action": "BUY", "symbol": "GDX", "qty": 1, '
        '"reasoning": "THESIS: miners have operating leverage to gold"}'
        ']}'
    )

    thesis = runtime._entry_thesis_for_order(
        _order("GLD"),
        {},
        {"reasoning": raw_payload, "action_summary": "BUY 1 GLD"},
    )

    assert thesis == "BUY GLD: BUY 1 GLD"
