from datetime import datetime, timezone

import pytest

from src.backtest.accounting.portfolio import PortfolioAccountant
from src.core.loss_review import build_loss_review, format_loss_review_for_prompt
from src.core.models.enums import OrderType, Side
from src.core.models.execution import Order
from src.pods.runtime.pod_runtime import PodRuntime


class _NS:
    def __init__(self, data):
        self._data = dict(data)

    def get(self, key, default=None):
        return self._data.get(key, default)


def _order(symbol: str, side: Side, qty: float = 1.0) -> Order:
    return Order(
        pod_id="equities",
        symbol=symbol,
        side=side,
        order_type=OrderType.MARKET,
        quantity=qty,
        timestamp=datetime(2026, 5, 11, tzinfo=timezone.utc),
        strategy_tag="loss_review_test",
    )


@pytest.mark.parametrize(
    ("pod_id", "symbol"),
    [
        ("equities", "SHEL"),
        ("fx", "FXE"),
        ("crypto", "ETH/USD"),
        ("commodities", "USO"),
    ],
)
def test_loss_review_restricts_new_risk_for_any_asset_class(pod_id, symbol):
    now = datetime(2026, 5, 11, 12, 0, tzinfo=timezone.utc)
    position = {
        "symbol": symbol,
        "qty": 2.0,
        "cost_basis": 100.0,
        "current_price": 96.0,
        "unrealized_pnl": -8.0,
        "entry_thesis": "THESIS: catalyst was expected to support the asset.",
    }

    review = build_loss_review(
        pod_id=pod_id,
        nav=984.0,
        starting_capital=1000.0,
        baseline_nav=1000.0,
        positions=[position],
        closed_trades=[],
        now=now,
        iteration=7,
    )

    assert review["status"] == "restricted"
    assert review["restriction"]["block_new_risk"] is True
    assert review["top_contributors"][0]["symbol"] == symbol
    assert "PM review required" in review["pm_defense_prompt"]
    assert pod_id in format_loss_review_for_prompt(review).lower()


def test_loss_review_stays_clear_inside_thresholds():
    review = build_loss_review(
        pod_id="crypto",
        nav=997.0,
        starting_capital=1000.0,
        baseline_nav=1000.0,
        positions=[{
            "symbol": "SOL/USD",
            "qty": 1.0,
            "cost_basis": 100.0,
            "current_price": 99.0,
            "unrealized_pnl": -1.0,
        }],
        closed_trades=[],
        now=datetime(2026, 5, 11, tzinfo=timezone.utc),
    )

    assert review["status"] == "clear"
    assert review["restriction"]["block_new_risk"] is False
    assert format_loss_review_for_prompt(review) == ""


def test_runtime_loss_review_blocks_new_risk_but_allows_reduction():
    acct = PortfolioAccountant(pod_id="equities", initial_nav=1000.0)
    acct.record_fill_direct("open", "SHEL", qty=2.0, fill_price=100.0)
    runtime = PodRuntime.__new__(PodRuntime)
    runtime._pod_id = "equities"
    runtime._ns = _NS({
        "loss_review_restriction": {
            "mode": "reduce_only",
            "block_new_risk": True,
            "reason": "Pod daily loss exceeded threshold",
        }
    })

    buy_allowed, buy_reason = runtime._loss_review_allows_order(_order("SHEL", Side.BUY), acct)
    sell_allowed, sell_reason = runtime._loss_review_allows_order(_order("SHEL", Side.SELL), acct)

    assert buy_allowed is False
    assert "blocked" in buy_reason.lower()
    assert sell_allowed is True
    assert sell_reason == ""
