from types import SimpleNamespace

from src.mission_control.session_manager import SessionManager


class _Namespace:
    def __init__(self, accountant):
        self._accountant = accountant

    def get(self, key):
        if key == "accountant":
            return self._accountant
        return None


def test_get_all_closed_trades_includes_date_aliases():
    manager = SessionManager.__new__(SessionManager)
    accountant = SimpleNamespace(
        closed_trades=[
            {
                "symbol": "GLD",
                "side": "long",
                "entry_price": 190.0,
                "exit_price": 187.5,
                "qty": 2,
                "realized_pnl": -5.0,
                "entry_time": "2026-04-01T14:30:00+00:00",
                "exit_time": "2026-04-03T16:00:00+00:00",
            }
        ]
    )
    manager._pod_runtimes = {"commodities": SimpleNamespace(_ns=_Namespace(accountant))}
    manager._restored_memory = {}

    rows = manager.get_all_closed_trades()

    assert rows[0]["entry_date"] == "2026-04-01"
    assert rows[0]["exit_date"] == "2026-04-03"
    assert rows[0]["holding_days"] == 2
