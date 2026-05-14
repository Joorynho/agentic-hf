from datetime import datetime, timezone
import pytest

from src.agents.investment_committee import InvestmentCommitteeReviewer
from src.agents.specialists import SpecialistRunner
from src.backtest.accounting.portfolio import PortfolioAccountant
from src.core.models.enums import OrderType, Side
from src.core.models.execution import Order
from src.core.research_feed import ResearchFeedStore
from src.data.services.foresight_service import ForesightService


def _order(symbol: str = "GLD", side: Side = Side.BUY, qty: float = 2.0, conviction: float = 0.8) -> Order:
    return Order(
        pod_id="commodities",
        symbol=symbol,
        side=side,
        order_type=OrderType.MARKET,
        quantity=qty,
        timestamp=datetime.now(timezone.utc),
        strategy_tag="test",
        conviction=conviction,
    )


def test_foresight_dedupes_routes_and_persists_catalysts(tmp_path):
    store = ResearchFeedStore(str(tmp_path / "research_feed.duckdb"))
    try:
        headline = {
            "title": "Hormuz oil shock lifts gold and weakens USD",
            "text": "WTI, GLD and USO react as shipping risk raises inflation uncertainty.",
            "url": "https://example.com/hormuz",
            "source": "Reuters",
            "category": "Commodities",
            "timestamp": "2026-05-13T09:00:00+00:00",
            "sentiment": 0.4,
        }
        assert store.record_items([headline, dict(headline)], "news") == 2

        service = ForesightService(feed_store=store)
        report = service.refresh(
            shared_data={"fred_snapshot": {"VIXCLS": 28.0, "T10Y2Y": -0.35, "DFII10": 1.9}},
            pod_contexts={
                "commodities": {"universe": ["GLD", "USO"], "held_symbols": []},
                "fx": {"universe": ["UUP", "FXE"], "held_symbols": []},
            },
        )

        event_ids = [event["event_id"] for event in report["events"]]
        assert len(event_ids) == len(set(event_ids))
        hormuz = next(event for event in report["events"] if "Hormuz" in event["title"])
        assert "commodities" in hormuz["affected_pods"]
        assert "fx" in hormuz["affected_pods"]
        assert {"GLD", "USO"}.intersection(set(hormuz["affected_symbols"]))
        assert hormuz["thread_id"].startswith("thread:")
        assert hormuz["materiality_score"] > 0
        assert "routing_reason" in hormuz
        assert hormuz["transmission_path"]

        persisted = service.get_report(limit=10)
        assert persisted["event_count"] >= 1
        assert any(event["event_id"] == hormuz["event_id"] for event in persisted["events"])
        threads = store.catalyst_threads(limit=10)
        assert threads
        assert threads[0]["event_count"] >= 1
    finally:
        store.close()


@pytest.mark.asyncio
async def test_specialist_runner_caps_requests_and_falls_back_without_llm(monkeypatch):
    monkeypatch.setattr("src.agents.specialists.has_llm_key", lambda: False)
    runner = SpecialistRunner()
    requests = [
        {
            "type": "macro_policy",
            "symbol": "GLD",
            "question": f"Question {idx}",
            "reason": "Need challenge",
            "related_catalyst_ids": ["cat-1"],
            "decision_impact": "Would change sizing",
            "required_data": "current macro data",
        }
        for idx in range(5)
    ]

    briefs = await runner.run_requests(
        pod_id="commodities",
        requests=requests,
        context={"foresight_events": [{"event_id": "cat-1", "title": "Gold catalyst"}]},
    )

    assert len(briefs) == 3
    assert all(brief["type"] == "macro_policy" for brief in briefs)
    assert all("brief_id" in brief for brief in briefs)
    assert all(brief["related_catalyst_ids"] == ["cat-1"] for brief in briefs)
    assert all("decision_impact" in brief for brief in briefs)


@pytest.mark.asyncio
async def test_committee_reviews_only_risk_increasing_and_can_reject_weak_trade(monkeypatch):
    monkeypatch.setattr("src.agents.investment_committee.has_llm_key", lambda: False)
    reviewer = InvestmentCommitteeReviewer()
    acct = PortfolioAccountant(pod_id="commodities", initial_nav=1_000.0)
    order = _order("GLD", Side.BUY, qty=2.0, conviction=0.8)

    should_review, triggers = reviewer.should_review(
        order=order,
        accountant=acct,
        matching_trade={"reasoning": ""},
        pm_decision={},
        thesis_gate_result={"quality_score": 0.2},
        quality_gate={"action": "block", "reason": "No thesis"},
    )
    assert should_review
    assert {"new_entry", "weak_or_stale_evidence"}.intersection(set(triggers))

    review = await reviewer.review(
        pod_id="commodities",
        order=order,
        accountant=acct,
        matching_trade={"reasoning": ""},
        pm_decision={},
        trade_reasoning="",
        thesis_gate_result={"quality_score": 0.2, "feedback": "No thesis"},
        quality_gate={"action": "block", "reason": "No thesis"},
        ctx={},
        triggers=triggers,
    )
    assert review.decision == "REJECT"
    assert review.reviewer_votes
    assert review.blockers

    acct.record_fill_direct("seed-order", "GLD", 2.0, 100.0, strategy_tag="seed")
    reduce_order = _order("GLD", Side.SELL, qty=1.0, conviction=0.5)
    should_review_reduce, _ = reviewer.should_review(
        order=reduce_order,
        accountant=acct,
        matching_trade={},
        pm_decision={},
        thesis_gate_result={"quality_score": 0.2},
        quality_gate={"action": "warn"},
    )
    assert should_review_reduce is False
