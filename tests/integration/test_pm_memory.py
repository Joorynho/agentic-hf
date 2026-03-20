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

def test_multiple_pods_isolated(audit_log):
    mem_eq = PMMemory("equities", audit_log)
    mem_cr = PMMemory("crypto", audit_log)
    mem_eq.record("BUY AAPL", "equity play", ["AAPL"])
    mem_cr.record("BUY BTC-USD", "crypto rally", ["BTC-USD"])
    eq_recall = mem_eq.recall()
    cr_recall = mem_cr.recall()
    assert "AAPL" in eq_recall
    assert "AAPL" not in cr_recall
    assert "BTC-USD" in cr_recall
