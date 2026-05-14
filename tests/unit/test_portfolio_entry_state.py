"""Entry thesis persistence on PortfolioAccountant."""

from datetime import datetime, timezone
from types import SimpleNamespace

from src.backtest.accounting.portfolio import PortfolioAccountant
from src.mission_control.session_manager import SessionManager


def test_to_state_dict_includes_entry_fields():
    acct = PortfolioAccountant(pod_id="fx", initial_nav=50_000.0)
    acct._entry_theses["EURUSD"] = "long dollar"
    acct._entry_dates["EURUSD"] = "2026-01-15"
    acct._entry_metadata["EURUSD"] = {"reasoning": "macro", "conviction": 0.7}
    d = acct.to_state_dict()
    assert d["entry_theses"]["EURUSD"] == "long dollar"
    assert d["entry_dates"]["EURUSD"] == "2026-01-15"
    assert d["entry_metadata"]["EURUSD"]["reasoning"] == "macro"


def test_load_entry_state_restores():
    acct = PortfolioAccountant(pod_id="fx", initial_nav=50_000.0)
    state = {
        "entry_theses": {"GBPUSD": "fade"},
        "entry_dates": {"GBPUSD": "2026-02-01"},
        "entry_metadata": {"GBPUSD": {"reasoning": "x", "conviction": 0.5}},
    }
    acct.load_entry_state(state)
    assert acct._entry_theses["GBPUSD"] == "fade"
    assert acct._entry_metadata["GBPUSD"]["conviction"] == 0.5


def test_record_fill_direct_uses_reasoning_as_entry_thesis():
    acct = PortfolioAccountant(pod_id="commodities", initial_nav=1_000.0)
    thesis = "THESIS: gold real yields falling | RISK: USD squeeze"

    acct.record_fill_direct(
        "order-1",
        "GLD",
        qty=1.0,
        fill_price=190.0,
        filled_at=datetime(2026, 4, 29, tzinfo=timezone.utc),
        reasoning=thesis,
    )

    assert acct.current_positions["GLD"].entry_thesis == thesis
    assert acct.to_state_dict()["entry_metadata"]["GLD"]["entry_thesis"] == thesis


def test_record_fill_direct_prefers_explicit_entry_thesis():
    acct = PortfolioAccountant(pod_id="equities", initial_nav=1_000.0)

    acct.record_fill_direct(
        "order-1",
        "SPY",
        qty=1.0,
        fill_price=500.0,
        reasoning="raw PM response",
        entry_thesis="THESIS: equity breadth improving",
    )

    assert acct.current_positions["SPY"].entry_thesis == "THESIS: equity breadth improving"
    assert acct._entry_metadata["SPY"]["reasoning"] == "raw PM response"


def test_record_fill_direct_persists_trade_evidence_packet():
    acct = PortfolioAccountant(pod_id="crypto", initial_nav=1_000.0)
    packet = {
        "version": 1,
        "symbol": "SOL/USD",
        "trade": {"side": "BUY", "qty": 1.0, "entry_thesis": "THESIS: verified catch-up trade"},
        "checks": [{"name": "market_data", "status": "PASS", "detail": "fresh price"}],
    }

    acct.record_fill_direct(
        "order-1",
        "SOL/USD",
        qty=1.0,
        fill_price=90.0,
        reasoning="THESIS: verified catch-up trade",
        evidence_packet=packet,
    )

    snap = acct.current_positions["SOL/USD"]
    state = acct.to_state_dict()

    assert snap.evidence_packet["trade"]["entry_thesis"] == "THESIS: verified catch-up trade"
    assert acct._fill_log[0]["evidence_packet"]["checks"][0]["name"] == "market_data"
    assert state["entry_metadata"]["SOL/USD"]["evidence_packet"]["symbol"] == "SOL/USD"


def test_load_entry_state_backfills_thesis_from_metadata_reasoning():
    acct = PortfolioAccountant(pod_id="fx", initial_nav=1_000.0)

    acct.load_entry_state({
        "entry_metadata": {
            "FXE": {
                "reasoning": "THESIS: dollar downside after dovish Fed repricing",
                "conviction": 0.7,
            }
        }
    })

    assert acct._entry_theses["FXE"] == "THESIS: dollar downside after dovish Fed repricing"
    assert acct._entry_metadata["FXE"]["entry_thesis"] == "THESIS: dollar downside after dovish Fed repricing"


class _Namespace:
    def __init__(self, accountant):
        self._accountant = accountant
        self._data = {}

    def get(self, key):
        if key == "accountant":
            return self._accountant
        return self._data.get(key)

    def set(self, key, value):
        self._data[key] = value


def test_positions_api_falls_back_to_metadata_reasoning_for_thesis():
    manager = SessionManager.__new__(SessionManager)
    acct = PortfolioAccountant(pod_id="commodities", initial_nav=1_000.0)
    acct.record_fill_direct("order-1", "SLV", qty=1.0, fill_price=25.0)
    acct._entry_theses["SLV"] = ""
    acct._entry_metadata["SLV"] = {
        "entry_time": "2026-04-29T10:00:00+00:00",
        "reasoning": "THESIS: silver beta to industrial recovery",
        "thesis_status": "challenged",
        "thesis_issues": ["Macro regime changed"],
        "thesis_review": {"status": "challenged", "issues": ["Macro regime changed"], "block_adds": True},
        "evidence_packet": {"symbol": "SLV", "checks": [{"name": "thesis_lifecycle", "status": "WATCH"}]},
    }
    manager._pod_runtimes = {"commodities": SimpleNamespace(_ns=_Namespace(acct))}

    rows = manager.get_all_positions()

    assert rows[0]["entry_thesis"] == "THESIS: silver beta to industrial recovery"
    assert rows[0]["thesis_status"] == "challenged"
    assert rows[0]["thesis_review"]["block_adds"] is True
    assert rows[0]["entry_notional"] == 25.0
    assert rows[0]["current_notional"] == rows[0]["notional"]
    assert rows[0]["notional_basis"] == "current_price"
    assert rows[0]["evidence_packet"]["symbol"] == "SLV"


def test_evidence_review_queue_flags_missing_and_weak_evidence():
    manager = SessionManager.__new__(SessionManager)
    acct = PortfolioAccountant(pod_id="crypto", initial_nav=1_000.0)
    acct.record_fill_direct("order-1", "SOL/USD", qty=1.0, fill_price=90.0)
    acct.record_fill_direct(
        "order-2",
        "ETH/USD",
        qty=0.1,
        fill_price=2300.0,
        evidence_packet={
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "trade": {"side": "BUY", "qty": 0.1, "entry_thesis": "THESIS: ETH beta"},
            "market_context": {"price_source": "CoinMarketCap", "price_age_seconds": 20},
            "checks": [{"name": "pre_trade_quality", "status": "WARN", "detail": "needs valuation evidence"}],
            "missing_evidence": ["Needs valuation evidence"],
            "evidence": {"top_news": [], "top_prediction_markets": []},
        },
    )
    manager._pod_runtimes = {"crypto": SimpleNamespace(_ns=_Namespace(acct))}

    queue = manager.get_evidence_review_queue()
    rows = {row["symbol"]: row for row in queue["queue"]}

    assert queue["status"] == "CHECK"
    assert rows["SOL/USD"]["status"] == "URGENT"
    assert "No evidence packet" in rows["SOL/USD"]["reasons"][0]
    assert rows["ETH/USD"]["status"] in {"WATCH", "REVIEW"}
    assert "Needs valuation evidence" in rows["ETH/USD"]["missing_evidence"]


def test_evidence_trade_guard_restricts_urgent_and_review_symbols():
    manager = SessionManager.__new__(SessionManager)
    acct = PortfolioAccountant(pod_id="crypto", initial_nav=1_000.0)
    acct.record_fill_direct("order-1", "SOL/USD", qty=1.0, fill_price=90.0)
    acct.record_fill_direct(
        "order-2",
        "ETH/USD",
        qty=0.1,
        fill_price=2300.0,
        evidence_packet={
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "trade": {"side": "BUY", "qty": 0.1, "entry_thesis": "THESIS: ETH beta"},
            "market_context": {"price_source": "CoinMarketCap", "price_age_seconds": 20},
            "checks": [{"name": "pre_trade_quality", "status": "WARN", "detail": "needs valuation evidence"}],
            "missing_evidence": ["Needs valuation evidence"],
            "evidence": {"top_news": [], "top_prediction_markets": []},
        },
    )
    ns = _Namespace(acct)
    manager._pod_runtimes = {"crypto": SimpleNamespace(_ns=ns)}

    review = manager.get_evidence_review_queue()
    guard = manager._apply_evidence_trade_guard(review)

    pod_guard = ns.get("evidence_trade_guard")
    assert guard["status"] == "CHECK"
    assert pod_guard["blocked_symbols"]["SOL/USD"]["status"] == "URGENT"
    assert pod_guard["blocked_symbols"]["SOL/USD"]["mode"] == "reduce_only"
    assert pod_guard["blocked_count"] >= 1
    assert "Evidence/thesis review queue" in ns.get("evidence_review_text")


def test_position_detail_backfills_all_buy_fill_theses_from_memory():
    manager = SessionManager.__new__(SessionManager)
    acct = PortfolioAccountant(pod_id="commodities", initial_nav=1_000.0)
    acct.load_positions([
        {"symbol": "GLD", "qty": 3.0, "avg_entry": 100.0, "current_price": 102.0}
    ])
    manager._pod_runtimes = {"commodities": SimpleNamespace(_ns=_Namespace(acct))}
    memory = {
        "trades": [
            {
                "pod_id": "commodities",
                "symbol": "GLD",
                "side": "buy",
                "qty": 2.0,
                "filled_price": 99.0,
                "timestamp": "2026-04-28T10:00:00+00:00",
                "order_id": "gld-entry",
                "entry_thesis": "THESIS: initial gold entry",
                "conviction": 0.7,
            },
            {
                "pod_id": "commodities",
                "symbol": "GLD",
                "side": "buy",
                "qty": 1.0,
                "filled_price": 101.0,
                "timestamp": "2026-04-29T11:30:00+00:00",
                "order_id": "gld-add",
                "entry_thesis": "THESIS: expansion after breakout confirmation",
                "conviction": 0.8,
            },
        ]
    }
    manager._restored_memory = memory

    manager._backfill_entry_metadata_from_memory(memory)
    detail = manager.get_position_detail("commodities", "GLD")

    assert detail is not None
    buy_fills = [f for f in detail["fills"] if f["side"] == "BUY"]
    assert [f["order_id"] for f in buy_fills] == ["gld-entry", "gld-add"]
    assert buy_fills[0]["entry_thesis"] == "THESIS: initial gold entry"
    assert buy_fills[1]["entry_thesis"] == "THESIS: expansion after breakout confirmation"
