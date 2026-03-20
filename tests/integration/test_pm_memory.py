import duckdb
import pytest
from unittest.mock import MagicMock
from src.core.pm_memory import PMMemory

@pytest.fixture
def audit_log(tmp_path):
    conn = duckdb.connect(str(tmp_path / "test.db"))
    log = MagicMock()
    log._conn = conn
    return log

def test_record_and_recall(audit_log):
    mem = PMMemory("equities", audit_log)
    mem.record("BUY AAPL, MSFT", "Tech sector showing strength", ["AAPL", "MSFT"])
    mem.record("HOLD", "No changes — thesis intact", ["AAPL"])
    result = mem.recall()
    assert "BUY AAPL, MSFT" in result
    assert "PAST DECISIONS" in result

def test_outcome_update(audit_log):
    mem = PMMemory("equities", audit_log)
    mem.record("BUY AAPL", "Strong momentum", ["AAPL"])
    mem.mark_outcome("AAPL", "win")
    result = mem.recall()
    assert "win" in result

def test_empty_recall(audit_log):
    mem = PMMemory("equities", audit_log)
    assert mem.recall() == ""

def test_outcome_not_overwritten(audit_log):
    mem = PMMemory("equities", audit_log)
    mem.record("BUY AAPL", "Strong momentum", ["AAPL"])
    mem.mark_outcome("AAPL", "win")
    mem.mark_outcome("AAPL", "loss")  # should NOT overwrite — already closed
    result = mem.recall()
    assert "win" in result
    assert "loss" not in result


def test_multiple_pods_isolated(audit_log):
    pods = ["equities", "crypto", "fx", "commodities"]
    memories = {p: PMMemory(p, audit_log) for p in pods}

    memories["equities"].record("BUY AAPL", "equity play", ["AAPL"])
    memories["crypto"].record("BUY BTC-USD", "crypto rally", ["BTC-USD"])
    memories["fx"].record("BUY EUR/USD", "fx move", ["EUR/USD"])
    memories["commodities"].record("BUY OIH", "oil demand", ["OIH"])

    eq_recall = memories["equities"].recall()
    cr_recall = memories["crypto"].recall()
    fx_recall = memories["fx"].recall()
    co_recall = memories["commodities"].recall()

    assert "AAPL" in eq_recall and "BTC-USD" not in eq_recall
    assert "BTC-USD" in cr_recall and "AAPL" not in cr_recall
    assert "EUR/USD" in fx_recall and "AAPL" not in fx_recall
    assert "OIH" in co_recall and "BTC-USD" not in co_recall
