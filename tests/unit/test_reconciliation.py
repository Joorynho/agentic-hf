from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from src.core.models.execution import PositionSnapshot
from src.mission_control.session_manager import SessionManager


class _FakeNamespace:
    def __init__(self, accountant, extra=None):
        self._data = {"accountant": accountant}
        if extra:
            self._data.update(extra)

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        self._data[key] = value


class _FakeRuntime:
    def __init__(self, accountant, extra=None):
        self._ns = _FakeNamespace(accountant, extra=extra)


class _FakeAccountant:
    def __init__(self, positions, fill_log=None):
        self.current_positions = positions
        self._fill_log = fill_log or []

    def to_state_dict(self):
        invested = sum(
            abs(float(pos.qty) * float(pos.current_price))
            for pos in self.current_positions.values()
        )
        starting_capital = 1000.0
        cash = starting_capital - invested
        return {
            "starting_capital": starting_capital,
            "nav": invested + cash,
            "cash": cash,
            "invested": invested,
            "positions": list(self.current_positions.values()),
        }


class _FakeAlpaca:
    def __init__(self):
        self.canceled: list[str] = []
        self.account = {"equity": 100000.0, "buying_power": 400000.0, "position_count": 1}
        self.positions = {}
        self.open_orders = []
        self.order_status = {}

    async def fetch_account(self):
        return self.account

    async def get_open_positions(self):
        return self.positions

    async def get_all_open_orders(self):
        return self.open_orders

    async def get_order_status(self, order_id):
        return self.order_status[order_id]

    async def cancel_order(self, order_id):
        self.canceled.append(order_id)
        return True


class _SlowAlpaca(_FakeAlpaca):
    def __init__(self):
        super().__init__()
        self.fetch_account_calls = 0
        self.position_calls = 0
        self.open_order_calls = 0

    async def fetch_account(self):
        self.fetch_account_calls += 1
        await asyncio.sleep(1)
        return self.account

    async def get_open_positions(self):
        self.position_calls += 1
        await asyncio.sleep(1)
        return self.positions

    async def get_all_open_orders(self):
        self.open_order_calls += 1
        await asyncio.sleep(1)
        return self.open_orders


def _manager(fake_alpaca: _FakeAlpaca) -> SessionManager:
    return SessionManager(alpaca_adapter=fake_alpaca, enable_news_adapters=False)


@pytest.mark.asyncio
async def test_broker_reconciliation_reports_qty_mismatch():
    alpaca = _FakeAlpaca()
    alpaca.positions = {
        "SOL/USD": {
            "qty": 0.5,
            "side": "long",
            "current_price": 150.0,
            "unrealized_pl": 3.0,
        }
    }
    sm = _manager(alpaca)
    sm._pod_runtimes = {
        "crypto": _FakeRuntime(_FakeAccountant({
            "SOL/USD": PositionSnapshot(
                symbol="SOL/USD",
                qty=0.4,
                cost_basis=140.0,
                current_price=150.0,
                unrealized_pnl=4.0,
            )
        }))
    }

    payload = await sm.get_broker_reconciliation()

    assert payload["status"] == "CHECK"
    assert payload["mismatches"][0]["symbol"] == "SOL/USD"
    assert payload["mismatches"][0]["status"] == "QTY_MISMATCH"
    assert payload["mismatches"][0]["qty_delta"] == pytest.approx(0.1)


@pytest.mark.asyncio
async def test_broker_reconciliation_matches_crypto_symbol_aliases():
    alpaca = _FakeAlpaca()
    alpaca.positions = {
        "SOLUSD": {
            "qty": 0.5,
            "side": "long",
            "current_price": 150.0,
            "unrealized_pl": 3.0,
        }
    }
    sm = _manager(alpaca)
    sm._pod_runtimes = {
        "crypto": _FakeRuntime(_FakeAccountant({
            "SOL/USD": PositionSnapshot(
                symbol="SOL/USD",
                qty=0.5,
                cost_basis=140.0,
                current_price=150.0,
                unrealized_pnl=5.0,
            )
        }))
    }

    payload = await sm.get_broker_reconciliation()

    assert payload["status"] == "OK"
    assert payload["positions"][0]["symbol"] == "SOL/USD"
    assert payload["positions"][0]["broker_symbol"] == "SOLUSD"


@pytest.mark.asyncio
async def test_state_health_does_not_block_on_live_broker_fetch():
    alpaca = _SlowAlpaca()
    sm = _manager(alpaca)
    sm._capital_per_pod = 1000.0
    sm._pod_capital = {"crypto": 1000.0}
    sm._session_active = True
    sm._pod_runtimes = {
        "crypto": _FakeRuntime(_FakeAccountant({
            "SOL/USD": PositionSnapshot(
                symbol="SOL/USD",
                qty=0.5,
                cost_basis=90.0,
                current_price=100.0,
                unrealized_pnl=5.0,
            )
        }))
    }

    payload = await asyncio.wait_for(sm.get_state_health(), timeout=0.1)

    assert alpaca.fetch_account_calls == 0
    assert payload["pods"][2]["pod_id"] == "crypto"
    assert payload["pods"][2]["nav"] == pytest.approx(1000.0)
    assert payload["broker"]["status"] == "UNKNOWN"


@pytest.mark.asyncio
async def test_broker_reconciliation_returns_local_rows_when_broker_times_out():
    alpaca = _SlowAlpaca()
    sm = _manager(alpaca)
    sm._broker_reconciliation_timeout_s = 0.01
    sm._pod_runtimes = {
        "crypto": _FakeRuntime(_FakeAccountant({
            "SOL/USD": PositionSnapshot(
                symbol="SOL/USD",
                qty=0.5,
                cost_basis=90.0,
                current_price=100.0,
                unrealized_pnl=5.0,
            )
        }))
    }

    payload = await asyncio.wait_for(sm.get_broker_reconciliation(), timeout=0.5)

    assert payload["status"] == "CHECK"
    assert payload["positions"][0]["symbol"] == "SOL/USD"
    assert payload["positions"][0]["status"] == "LOCAL_ONLY"
    assert payload["positions"][0]["local_qty"] == pytest.approx(0.5)
    assert any("timed out" in err for err in payload["errors"])


def test_execution_quality_counts_missing_slippage_data():
    alpaca = _FakeAlpaca()
    sm = _manager(alpaca)
    sm._pod_runtimes = {
        "crypto": _FakeRuntime(_FakeAccountant({}, fill_log=[
            {"symbol": "SOL/USD", "slippage_bps": None},
            {"symbol": "ETH/USD", "slippage_bps": 1.5},
        ]))
    }

    quality = sm._compute_execution_quality()

    assert quality["crypto"]["total_fills"] == 2
    assert quality["crypto"]["fills_with_slippage_data"] == 1
    assert quality["crypto"]["fills_missing_slippage_data"] == 1


def test_data_quality_report_flags_missing_or_stale_position_prices():
    alpaca = _FakeAlpaca()
    sm = _manager(alpaca)
    sm._pod_runtimes = {
        "crypto": _FakeRuntime(_FakeAccountant({
            "SOL/USD": PositionSnapshot(
                symbol="SOL/USD",
                qty=0.5,
                cost_basis=90.0,
                current_price=90.0,
                unrealized_pnl=0.0,
                price_source="",
                price_updated_at="",
                price_stale=True,
            )
        }))
    }

    report = sm.get_data_quality_report()

    assert report["status"] == "CHECK"
    assert report["position_count"] == 1
    assert report["check_count"] == 1
    assert report["stale_price_count"] == 1
    assert report["missing_source_count"] == 1
    assert report["positions"][0]["symbol"] == "SOL/USD"
    assert "missing price source" in report["positions"][0]["issues"]


@pytest.mark.asyncio
async def test_execution_reconciliation_turns_pending_order_into_rejected_update():
    alpaca = _FakeAlpaca()
    alpaca.order_status = {
        "ord-1": {
            "status": "rejected",
            "symbol": "SOL/USD",
            "side": "buy",
            "filled_qty": 0.0,
            "filled_avg_price": None,
            "reason": "invalid crypto time_in_force",
        }
    }
    sm = _manager(alpaca)

    payload = await sm.reconcile_execution_state(local_orders=[{
        "data": {
            "order_id": "ord-1",
            "pod_id": "crypto",
            "symbol": "SOL/USD",
            "side": "BUY",
            "qty": 0.5,
            "status": "PENDING",
        }
    }])

    assert payload["checked_local_orders"] == 1
    assert payload["updates"][0]["status"] == "REJECTED"
    assert payload["updates"][0]["stage"] == "broker_reconcile"
    assert payload["updates"][0]["reason"] == "invalid crypto time_in_force"


@pytest.mark.asyncio
async def test_execution_reconciliation_skips_local_pending_without_broker_id():
    alpaca = _FakeAlpaca()
    sm = _manager(alpaca)

    payload = await sm.reconcile_execution_state(local_orders=[{
        "data": {
            "order_id": "local-1",
            "local_order_id": "local-1",
            "broker_order_id": None,
            "pod_id": "crypto",
            "symbol": "SOL/USD",
            "side": "BUY",
            "qty": 0.5,
            "status": "PENDING",
        }
    }])

    assert payload["checked_local_orders"] == 0
    assert payload["updates"] == []


@pytest.mark.asyncio
async def test_execution_reconciliation_cancels_stale_open_broker_orders():
    alpaca = _FakeAlpaca()
    alpaca.open_orders = [{
        "order_id": "stale-1",
        "symbol": "SHEL",
        "side": "buy",
        "qty": 1.0,
        "status": "accepted",
        "submitted_at": datetime.now(timezone.utc) - timedelta(minutes=5),
    }]
    sm = _manager(alpaca)

    payload = await sm.reconcile_execution_state(cancel_stale_after_s=60)

    assert alpaca.canceled == ["stale-1"]
    assert payload["canceled_stale_orders"][0]["order_id"] == "stale-1"
    assert payload["canceled_stale_orders"][0]["status"] == "REJECTED"
    assert "canceled after" in payload["canceled_stale_orders"][0]["reason"]


def test_execution_truth_reports_latest_runtime_block():
    alpaca = _FakeAlpaca()
    sm = _manager(alpaca)
    sm._pod_runtimes = {
        "crypto": _FakeRuntime(_FakeAccountant({}), extra={
            "last_pm_decision": {
                "trades": [{
                    "action": "BUY",
                    "symbol": "SOL/USD",
                    "qty": 0.5,
                    "reasoning": "Fresh thesis",
                }],
                "action_summary": "BUY SOL/USD",
            },
            "last_trade_block": {
                "pod_id": "crypto",
                "symbol": "SOL/USD",
                "side": "BUY",
                "status": "BLOCKED",
                "stage": "data_quality",
                "reason": "No positive live price available",
                "local_order_id": "local-1",
            },
            "thesis_gate_result": {"passed": True, "quality_score": 0.9, "feedback": ""},
            "last_data_quality_check": {
                "passed": False,
                "symbol": "SOL/USD",
                "issues": ["No positive live price available"],
            },
        })
    }

    payload = sm.get_execution_truth()
    crypto = [row for row in payload["pods"] if row["pod_id"] == "crypto"][0]

    assert payload["status"] == "CHECK"
    assert crypto["status"] == "BLOCKED"
    assert crypto["stage"] == "data_quality"
    assert crypto["reason"] == "No positive live price available"
