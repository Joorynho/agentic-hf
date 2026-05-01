from datetime import datetime, timezone

import pytest

from src.backtest.accounting.portfolio import PortfolioAccountant
from src.core.bus.event_bus import EventBus
from src.core.models.enums import OrderType, Side
from src.core.models.execution import Order
from src.pods.base.namespace import PodNamespace
from src.pods.templates.commodities.risk_agent import CommoditiesRiskAgent


def _agent_with_accountant(accountant: PortfolioAccountant) -> CommoditiesRiskAgent:
    ns = PodNamespace("commodities")
    ns.set("accountant", accountant)
    return CommoditiesRiskAgent(
        agent_id="commodities.risk",
        pod_id="commodities",
        namespace=ns,
        bus=EventBus(),
    )


def _order(symbol: str, side: Side, qty: float) -> Order:
    return Order(
        pod_id="commodities",
        symbol=symbol,
        side=side,
        order_type=OrderType.MARKET,
        quantity=qty,
        timestamp=datetime.now(timezone.utc),
        strategy_tag="test",
        conviction=0.8,
    )


@pytest.mark.asyncio
async def test_blocks_new_gold_miner_buy_when_gold_beta_already_breached():
    acct = PortfolioAccountant(pod_id="commodities", initial_nav=1000.0)
    acct.record_fill_direct("o1", "GLD", 3, 100.0, datetime.now(timezone.utc))
    acct.record_fill_direct("o2", "GDXJ", 3, 100.0, datetime.now(timezone.utc))
    agent = _agent_with_accountant(acct)

    result = await agent.run_cycle({"order": _order("GDX", Side.BUY, 1)})

    assert "token" not in result
    assert "Factor concentration" in result["reason"]
    assert "gold_beta" in result["reason"]


@pytest.mark.asyncio
async def test_reduce_only_blocks_buys_when_loaded_positions_exceed_nav():
    acct = PortfolioAccountant(pod_id="commodities", initial_nav=1000.0)
    acct.load_positions([
        {"symbol": "GLD", "qty": 6, "avg_entry": 100.0, "current_price": 100.0},
        {"symbol": "USO", "qty": 6, "avg_entry": 100.0, "current_price": 100.0},
    ])
    acct.reconcile_capital_from_positions(1000.0)
    agent = _agent_with_accountant(acct)

    result = await agent.run_cycle({"order": _order("DBA", Side.BUY, 1)})

    assert "token" not in result
    assert "Reduce-only mode" in result["reason"]


@pytest.mark.asyncio
async def test_reduce_only_allows_risk_reducing_sell():
    acct = PortfolioAccountant(pod_id="commodities", initial_nav=1000.0)
    acct.load_positions([
        {"symbol": "GLD", "qty": 6, "avg_entry": 100.0, "current_price": 100.0},
        {"symbol": "USO", "qty": 6, "avg_entry": 100.0, "current_price": 100.0},
    ])
    acct.reconcile_capital_from_positions(1000.0)
    agent = _agent_with_accountant(acct)

    result = await agent.run_cycle({"order": _order("GLD", Side.SELL, 1)})

    assert result.get("token") is not None


@pytest.mark.asyncio
async def test_unclassified_new_symbol_is_rejected_before_buy():
    acct = PortfolioAccountant(pod_id="commodities", initial_nav=1000.0)
    agent = _agent_with_accountant(acct)

    result = await agent.run_cycle({"order": _order("NEWOIL", Side.BUY, 1)})

    assert "token" not in result
    assert "no validated commodities factor map" in result["reason"]
