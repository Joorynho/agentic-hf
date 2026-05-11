from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from src.backtest.accounting.portfolio import PortfolioAccountant
from src.core.models.enums import OrderType, Side
from src.core.models.execution import Order, VerificationResult
from src.core.models.market import Bar
from src.pods.runtime.pod_runtime import PodRuntime


def _order(symbol: str = "GLD", side: Side = Side.BUY) -> Order:
    return Order(
        pod_id="commodities",
        symbol=symbol,
        side=side,
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


class _NS:
    def __init__(self, accountant):
        self._data = {"accountant": accountant}

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        self._data[key] = value


class _Bus:
    def __init__(self):
        self.messages = []

    async def publish(self, topic, message, publisher_id=None):
        self.messages.append((topic, message, publisher_id))


class _Agent:
    def __init__(self, fn):
        self.fn = fn
        self.calls = 0

    async def run_cycle(self, ctx):
        self.calls += 1
        return self.fn(ctx)


@pytest.mark.asyncio
async def test_runtime_blocks_buy_when_thesis_gate_fails(monkeypatch):
    acct = PortfolioAccountant(pod_id="commodities", initial_nav=1_000.0)
    ns = _NS(acct)
    bus = _Bus()
    runtime = PodRuntime("commodities", ns, SimpleNamespace(), bus)

    order = _order("GLD")

    def pm_fn(ctx):
        ns.set("last_pm_decision", {
            "trades": [{
                "action": "BUY",
                "symbol": "GLD",
                "qty": 1,
                "conviction": 0.8,
                "reasoning": "THESIS: inflation is high. RISK: rates.",
            }],
            "reasoning": "weak",
            "action_summary": "BUY 1 GLD",
        })
        return {"order": order}

    runtime.set_agents(
        researcher=_Agent(lambda ctx: {}),
        signal=_Agent(lambda ctx: {
            "features": {
                "fred_indicators": {"DFII10": 1.96, "T10YIE": 2.46},
                "regime": {"regime": "neutral", "label": "Neutral"},
            }
        }),
        pm=_Agent(pm_fn),
        risk=_Agent(lambda ctx: {"token": SimpleNamespace(is_valid=lambda: True)}),
        exec_trader=_Agent(lambda ctx: {"order_executed": True}),
        ops=_Agent(lambda ctx: {}),
    )

    async def always_fail(self, pm_decision, asset_class=""):
        return VerificationResult(passed=False, quality_score=0.2, feedback="weak thesis")

    monkeypatch.setattr("src.agents.thesis_verifier.ThesisVerifier.verify_with_llm", always_fail)

    await runtime.run_cycle(
        Bar(
            symbol="GLD",
            timestamp=datetime(2026, 5, 6, tzinfo=timezone.utc),
            open=100,
            high=101,
            low=99,
            close=100,
            volume=1000,
            source="test",
        ),
        skip_researcher=True,
    )

    assert ns.get("thesis_gate_result")["passed"] is False
    block = ns.get("last_trade_block")
    assert block["stage"] == "thesis_gate"
    assert block["local_order_id"] == str(order.id)
    assert runtime._risk.calls == 0
    assert runtime._exec_trader.calls == 0


@pytest.mark.asyncio
async def test_runtime_blocks_buy_when_existing_position_price_is_stale(monkeypatch):
    acct = PortfolioAccountant(pod_id="commodities", initial_nav=1_000.0)
    acct.load_positions([{
        "symbol": "GLD",
        "qty": 1.0,
        "avg_entry": 100.0,
        "current_price": 101.0,
        "price_source": "broker",
    }])
    acct._last_price_updated_at["GLD"] = datetime.now(timezone.utc) - timedelta(minutes=30)
    ns = _NS(acct)
    bus = _Bus()
    runtime = PodRuntime("commodities", ns, SimpleNamespace(), bus)

    order = _order("GLD", Side.BUY)

    def pm_fn(ctx):
        ns.set("last_pm_decision", {
            "trades": [{
                "action": "BUY",
                "symbol": "GLD",
                "qty": 1,
                "conviction": 0.8,
                "reasoning": "THESIS: fresh macro setup after pullback. RISK: rates and dollar.",
            }],
            "reasoning": "BUY 1 GLD",
            "action_summary": "BUY 1 GLD",
        })
        return {"order": order}

    runtime.set_agents(
        researcher=_Agent(lambda ctx: {}),
        signal=_Agent(lambda ctx: {"features": {"regime": {"label": "Neutral"}}}),
        pm=_Agent(pm_fn),
        risk=_Agent(lambda ctx: {"token": SimpleNamespace(is_valid=lambda: True)}),
        exec_trader=_Agent(lambda ctx: {"order_executed": True}),
        ops=_Agent(lambda ctx: {}),
    )

    async def always_pass(self, pm_decision, asset_class=""):
        return VerificationResult(passed=True, quality_score=0.9, feedback="")

    monkeypatch.setattr("src.agents.thesis_verifier.ThesisVerifier.verify_with_llm", always_pass)
    monkeypatch.setattr(
        "src.pods.runtime.pod_runtime.expansion_thesis_is_fresh",
        lambda reasoning, review: (True, ""),
    )

    await runtime.run_cycle(
        Bar(
            symbol="GLD",
            timestamp=datetime.now(timezone.utc),
            open=100,
            high=101,
            low=99,
            close=101,
            volume=1000,
            source="test",
        ),
        skip_researcher=True,
    )

    failure = ns.get("data_quality_failures")[0]
    assert failure["symbol"] == "GLD"
    assert "stale" in "; ".join(failure["issues"])
    block = ns.get("last_trade_block")
    assert block["stage"] == "data_quality"
    assert block["local_order_id"] == str(order.id)
    assert runtime._risk.calls == 0
    assert runtime._exec_trader.calls == 0


@pytest.mark.asyncio
async def test_runtime_allows_sell_when_existing_position_price_is_stale(monkeypatch):
    acct = PortfolioAccountant(pod_id="commodities", initial_nav=1_000.0)
    acct.load_positions([{
        "symbol": "GLD",
        "qty": 1.0,
        "avg_entry": 100.0,
        "current_price": 101.0,
        "price_source": "broker",
    }])
    acct._last_price_updated_at["GLD"] = datetime.now(timezone.utc) - timedelta(minutes=30)
    ns = _NS(acct)
    bus = _Bus()
    runtime = PodRuntime("commodities", ns, SimpleNamespace(), bus)

    order = _order("GLD", Side.SELL)

    def pm_fn(ctx):
        ns.set("last_pm_decision", {
            "trades": [{
                "action": "SELL",
                "symbol": "GLD",
                "qty": 1,
                "conviction": 0.8,
                "reasoning": "THESIS: reduce exposure while pricing feed is stale.",
            }],
            "reasoning": "SELL 1 GLD",
            "action_summary": "SELL 1 GLD",
        })
        return {"order": order}

    runtime.set_agents(
        researcher=_Agent(lambda ctx: {}),
        signal=_Agent(lambda ctx: {"features": {"regime": {"label": "Neutral"}}}),
        pm=_Agent(pm_fn),
        risk=_Agent(lambda ctx: {"token": SimpleNamespace(is_valid=lambda: True)}),
        exec_trader=_Agent(lambda ctx: {"order_executed": True}),
        ops=_Agent(lambda ctx: {}),
    )

    async def always_pass(self, pm_decision, asset_class=""):
        return VerificationResult(passed=True, quality_score=0.9, feedback="")

    monkeypatch.setattr("src.agents.thesis_verifier.ThesisVerifier.verify_with_llm", always_pass)

    await runtime.run_cycle(
        Bar(
            symbol="GLD",
            timestamp=datetime.now(timezone.utc),
            open=100,
            high=101,
            low=99,
            close=101,
            volume=1000,
            source="test",
        ),
        skip_researcher=True,
    )

    assert ns.get("data_quality_failures") is None
    assert runtime._risk.calls == 1
    assert runtime._exec_trader.calls == 1
