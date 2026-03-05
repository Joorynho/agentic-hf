import pytest
import time
from datetime import datetime
from uuid import uuid4

from src.execution.paper.paper_adapter import PaperAdapter
from src.core.models.execution import Order, RiskApprovalToken, RejectedOrder
from src.core.models.market import Bar
from src.core.models.enums import Side, OrderType


@pytest.mark.asyncio
async def test_paper_adapter_fills_market_order():
    adapter = PaperAdapter(tcm_bps=5.0, slippage_model="fixed")
    bar = Bar(
        symbol="AAPL", timestamp=datetime.now(), open=185.0, high=186.5,
        low=184.2, close=186.0, volume=50_000_000, adj_close=186.0, source="paper",
    )
    order = Order(
        pod_id="alpha", symbol="AAPL", side=Side.BUY,
        order_type=OrderType.MARKET, quantity=100,
        limit_price=None, timestamp=datetime.now(), strategy_tag="test",
    )
    token = RiskApprovalToken(pod_id="alpha", order_id=order.id)
    fill = await adapter.execute(order, token, bar)
    assert fill.quantity == 100
    assert fill.price > 0
    assert fill.commission > 0


@pytest.mark.asyncio
async def test_paper_adapter_rejects_expired_token():
    adapter = PaperAdapter(tcm_bps=5.0)
    bar = Bar(
        symbol="AAPL", timestamp=datetime.now(), open=185.0, high=186.5,
        low=184.2, close=186.0, volume=1e6, adj_close=186.0, source="paper",
    )
    order = Order(
        pod_id="alpha", symbol="AAPL", side=Side.BUY,
        order_type=OrderType.MARKET, quantity=100,
        limit_price=None, timestamp=datetime.now(), strategy_tag="test",
    )
    token = RiskApprovalToken(pod_id="alpha", order_id=order.id, expires_ms=1)
    time.sleep(0.01)
    result = await adapter.execute(order, token, bar)
    assert isinstance(result, RejectedOrder)
    assert "expired" in result.reason.lower()
