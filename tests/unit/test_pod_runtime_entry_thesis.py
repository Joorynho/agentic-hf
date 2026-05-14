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


def test_trade_evidence_packet_is_asset_agnostic_and_records_checks():
    acct = PortfolioAccountant(pod_id="crypto", initial_nav=1_000.0)
    ns = _NS(acct)
    ns.set("broker_trade_guard", {"status": "OK"})
    ns.set("execution_cooldown", {"active": False})
    runtime = PodRuntime("crypto", ns, SimpleNamespace(), _Bus())

    packet = runtime._build_trade_evidence_packet(
        order=_order("SOL/USD"),
        matching_trade={
            "symbol": "SOL/USD",
            "reasoning": "THESIS: SOL catch-up if on-chain activity confirms. INVALIDATION: ETH leads alone.",
            "exit_when": "SOL fails to hold breakout",
            "take_profit_levels": [{"trigger_pct": 0.08, "close_pct": 0.25}],
        },
        pm_decision={
            "action_summary": "BUY SOL/USD",
            "llm": {"provider": "OpenAI", "model": "gpt-5-mini", "task": "pm_decision"},
            "signal_snapshot": {"momentum": "positive"},
        },
        ctx={
            "features": {
                "macro_score": 0.32,
                "macro_outlook": "risk-on",
                "regime": {"label": "Risk-On"},
                "fred_indicators": {"DFII10": 1.96},
                "news_headlines": [{"title": "Solana DEX volume rises", "source": "test"}],
                "polymarket_predictions": [{"question": "Crypto risk appetite?", "probability": 0.61}],
            },
            "sizing_context": {"nav": 1000.0, "cash": 700.0, "invested": 300.0},
        },
        accountant=acct,
        trade_reasoning="THESIS: SOL catch-up if on-chain activity confirms. INVALIDATION: ETH leads alone.",
        thesis_gate_result={"passed": True, "quality_score": 0.82, "feedback": ""},
        quality_gate={"status": "WARN", "quality_score": 0.82, "reason": "Needs TVL evidence", "warnings": ["Needs TVL evidence"]},
        data_quality={"passed": True, "price": 90.0, "price_source": "CoinMarketCap", "price_age_seconds": 12},
        thesis_review={"status": "valid", "score": 0.8, "issues": [], "monitors": ["relative SOL/ETH strength"]},
        entry_macro_regime="risk-on",
    )

    assert packet["pod_id"] == "crypto"
    assert packet["symbol"] == "SOL/USD"
    assert packet["market_context"]["price_source"] == "CoinMarketCap"
    assert any(check["name"] == "pre_trade_quality" for check in packet["checks"])
    assert "Needs TVL evidence" in packet["missing_evidence"]


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
    assert block["stage"] == "quality_gate"
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
async def test_runtime_evidence_guard_makes_urgent_holding_reduce_only(monkeypatch):
    acct = PortfolioAccountant(pod_id="crypto", initial_nav=1_000.0)
    acct.load_positions([{
        "symbol": "SOL/USD",
        "qty": 1.0,
        "avg_entry": 90.0,
        "current_price": 91.0,
        "price_source": "CoinMarketCap",
    }])
    ns = _NS(acct)
    ns.set("evidence_trade_guard", {
        "status": "CHECK",
        "mode": "reduce_only",
        "blocked_symbols": {
            "SOL/USD": {
                "status": "URGENT",
                "mode": "reduce_only",
                "block_new_risk": True,
                "reason": "URGENT evidence review for SOL/USD: no evidence packet",
            }
        },
    })
    bus = _Bus()
    runtime = PodRuntime("crypto", ns, SimpleNamespace(), bus)
    order = Order(
        pod_id="crypto",
        symbol="SOL/USD",
        side=Side.BUY,
        order_type=OrderType.MARKET,
        quantity=0.5,
        timestamp=datetime.now(timezone.utc),
        strategy_tag="llm_pm",
        conviction=0.8,
    )

    def pm_fn(ctx):
        ns.set("last_pm_decision", {
            "trades": [{
                "action": "BUY",
                "symbol": "SOL/USD",
                "qty": 0.5,
                "conviction": 0.8,
                "reasoning": (
                    "THESIS: updated expansion thesis after fresh on-chain evidence. "
                    "ENTRY: add on confirmed breakout. INVALIDATION: risk off. RISK: size small."
                ),
            }],
            "reasoning": "BUY 0.5 SOL/USD",
            "action_summary": "BUY 0.5 SOL/USD",
        })
        return {"order": order}

    runtime.set_agents(
        researcher=_Agent(lambda ctx: {}),
        signal=_Agent(lambda ctx: {"features": {"regime": {"label": "Risk-On"}}}),
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
            symbol="SOL/USD",
            timestamp=datetime.now(timezone.utc),
            open=90,
            high=92,
            low=89,
            close=91,
            volume=1000,
            source="test",
        ),
        skip_researcher=True,
    )

    block = ns.get("last_trade_block")
    assert block["stage"] == "evidence_review"
    assert "reduce-only" in block["reason"]
    assert runtime._risk.calls == 0
    assert runtime._exec_trader.calls == 0


@pytest.mark.asyncio
async def test_runtime_evidence_guard_allows_reducing_urgent_holding(monkeypatch):
    acct = PortfolioAccountant(pod_id="crypto", initial_nav=1_000.0)
    acct.load_positions([{
        "symbol": "SOL/USD",
        "qty": 1.0,
        "avg_entry": 90.0,
        "current_price": 91.0,
        "price_source": "CoinMarketCap",
    }])
    acct._last_price_updated_at["SOL/USD"] = datetime.now(timezone.utc)
    ns = _NS(acct)
    ns.set("evidence_trade_guard", {
        "status": "CHECK",
        "mode": "reduce_only",
        "blocked_symbols": {
            "SOL/USD": {
                "status": "URGENT",
                "mode": "reduce_only",
                "block_new_risk": True,
                "reason": "URGENT evidence review for SOL/USD: no evidence packet",
            }
        },
    })
    bus = _Bus()
    runtime = PodRuntime("crypto", ns, SimpleNamespace(), bus)
    order = Order(
        pod_id="crypto",
        symbol="SOL/USD",
        side=Side.SELL,
        order_type=OrderType.MARKET,
        quantity=0.5,
        timestamp=datetime.now(timezone.utc),
        strategy_tag="llm_pm_reduce",
        conviction=0.8,
    )

    def pm_fn(ctx):
        ns.set("last_pm_decision", {
            "trades": [{
                "action": "SELL",
                "symbol": "SOL/USD",
                "qty": 0.5,
                "conviction": 0.8,
                "reasoning": "Reduce exposure while evidence review is urgent.",
            }],
            "reasoning": "SELL 0.5 SOL/USD",
            "action_summary": "SELL 0.5 SOL/USD",
        })
        return {"order": order}

    runtime.set_agents(
        researcher=_Agent(lambda ctx: {}),
        signal=_Agent(lambda ctx: {"features": {"regime": {"label": "Risk-On"}}}),
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
            symbol="SOL/USD",
            timestamp=datetime.now(timezone.utc),
            open=90,
            high=92,
            low=89,
            close=91,
            volume=1000,
            source="test",
        ),
        skip_researcher=True,
    )

    block = ns.get("last_trade_block") or {}
    assert block.get("stage") != "evidence_review"
    assert runtime._risk.calls == 1
    assert runtime._exec_trader.calls == 1


@pytest.mark.asyncio
async def test_runtime_evidence_guard_blocks_review_add_without_refreshed_thesis(monkeypatch):
    acct = PortfolioAccountant(pod_id="crypto", initial_nav=1_000.0)
    acct.load_positions([{
        "symbol": "ETH/USD",
        "qty": 0.1,
        "avg_entry": 2300.0,
        "current_price": 2310.0,
        "price_source": "CoinMarketCap",
    }])
    ns = _NS(acct)
    ns.set("evidence_trade_guard", {
        "status": "CHECK",
        "mode": "refresh_required",
        "blocked_symbols": {
            "ETH/USD": {
                "status": "REVIEW",
                "mode": "refresh_required",
                "block_new_risk": True,
                "requires_thesis_refresh": True,
                "allow_add_after_refresh": True,
                "reason": "REVIEW evidence review for ETH/USD: missing valuation evidence",
            }
        },
    })
    bus = _Bus()
    runtime = PodRuntime("crypto", ns, SimpleNamespace(), bus)
    order = Order(
        pod_id="crypto",
        symbol="ETH/USD",
        side=Side.BUY,
        order_type=OrderType.MARKET,
        quantity=0.05,
        timestamp=datetime.now(timezone.utc),
        strategy_tag="llm_pm",
        conviction=0.8,
    )

    def pm_fn(ctx):
        ns.set("last_pm_decision", {
            "trades": [{
                "action": "BUY",
                "symbol": "ETH/USD",
                "qty": 0.05,
                "conviction": 0.8,
                "reasoning": "THESIS: ETH is strong. RISK: volatility.",
            }],
            "reasoning": "BUY 0.05 ETH/USD",
            "action_summary": "BUY 0.05 ETH/USD",
        })
        return {"order": order}

    runtime.set_agents(
        researcher=_Agent(lambda ctx: {}),
        signal=_Agent(lambda ctx: {"features": {"regime": {"label": "Risk-On"}}}),
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
            symbol="ETH/USD",
            timestamp=datetime.now(timezone.utc),
            open=2300,
            high=2320,
            low=2290,
            close=2310,
            volume=1000,
            source="test",
        ),
        skip_researcher=True,
    )

    block = ns.get("last_trade_block")
    assert block["stage"] == "evidence_review"
    assert "fresh expansion thesis" in block["reason"]
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
