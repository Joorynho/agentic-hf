from datetime import datetime, timezone

from src.core.bus.event_bus import EventBus
from src.core.models.enums import OrderType, Side
from src.core.models.execution import Order
from src.pods.base.namespace import PodNamespace
from src.pods.runtime.pod_runtime import PodRuntime


def _runtime() -> PodRuntime:
    return PodRuntime("equities", PodNamespace("equities"), None, EventBus())  # type: ignore[arg-type]


def _order(side: Side = Side.BUY, conviction: float = 0.7) -> Order:
    return Order(
        pod_id="equities",
        symbol="XLE",
        side=side,
        order_type=OrderType.MARKET,
        quantity=1.0,
        timestamp=datetime.now(timezone.utc),
        strategy_tag="test",
        conviction=conviction,
    )


def test_quality_gate_warns_but_does_not_block_medium_thesis_score():
    runtime = _runtime()
    gate = runtime._pre_trade_quality_gate(
        order=_order(),
        matching_trade={"reasoning": "THESIS: Energy is gaining momentum. ENTRY: buy on confirmed breakout."},
        pm_decision={"reasoning": ""},
        thesis_gate_result={"passed": False, "quality_score": 0.55, "feedback": "Add invalidation."},
        trade_reasoning="THESIS: Energy is gaining momentum. ENTRY: buy on confirmed breakout.",
    )

    assert gate["action"] == "warn"
    assert "Add invalidation" in gate["reason"]


def test_quality_gate_blocks_critically_low_thesis_score():
    runtime = _runtime()
    gate = runtime._pre_trade_quality_gate(
        order=_order(),
        matching_trade={"reasoning": "buy looks good"},
        pm_decision={},
        thesis_gate_result={"passed": False, "quality_score": 0.2, "feedback": "Generic thesis."},
        trade_reasoning="buy looks good",
    )

    assert gate["action"] == "block"


def test_quality_gate_does_not_block_sell_exits():
    runtime = _runtime()
    gate = runtime._pre_trade_quality_gate(
        order=_order(side=Side.SELL),
        matching_trade={},
        pm_decision={},
        thesis_gate_result={"passed": False, "quality_score": 0.0, "feedback": "No thesis."},
        trade_reasoning="",
    )

    assert gate["action"] == "pass"


def test_quality_gate_warns_on_unsupported_relative_value_claim_without_blocking():
    runtime = _runtime()
    reasoning = (
        "THESIS: XLE is undervalued and should rally. ENTRY: buy now. "
        "INVALIDATION: price breaks support. RISK: oil volatility."
    )
    gate = runtime._pre_trade_quality_gate(
        order=_order(),
        matching_trade={"reasoning": reasoning},
        pm_decision={},
        thesis_gate_result={"passed": True, "quality_score": 0.7, "feedback": ""},
        trade_reasoning=reasoning,
    )

    assert gate["action"] == "warn"
    assert "Valuation or relative-value claim needs a supporting metric" in gate["reason"]
