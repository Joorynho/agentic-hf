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

    def get(self, key):
        if key == "accountant":
            return self._accountant
        return None


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
    }
    manager._pod_runtimes = {"commodities": SimpleNamespace(_ns=_Namespace(acct))}

    rows = manager.get_all_positions()

    assert rows[0]["entry_thesis"] == "THESIS: silver beta to industrial recovery"
    assert rows[0]["thesis_status"] == "challenged"
    assert rows[0]["thesis_review"]["block_adds"] is True
    assert rows[0]["entry_notional"] == 25.0
    assert rows[0]["current_notional"] == rows[0]["notional"]
    assert rows[0]["notional_basis"] == "current_price"


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
