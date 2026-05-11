from __future__ import annotations

import pytest

from src.backtest.accounting.portfolio import PortfolioAccountant
from src.data.adapters.price_service import PriceService, symbol_aliases
from src.mission_control.session_manager import SessionManager


class _NoCmc:
    def is_configured(self):
        return False


class _NoAv:
    def is_configured(self):
        return False


class _Namespace:
    def __init__(self, accountant):
        self._accountant = accountant
        self._store: dict = {}

    def get(self, key, default=None):
        if key == "accountant":
            return self._accountant
        return self._store.get(key, default)

    def set(self, key, value):
        self._store[key] = value


class _Runtime:
    def __init__(self, accountant):
        self._ns = _Namespace(accountant)


class _FakeAlpaca:
    def __init__(self, positions, quotes=None):
        self.positions = positions
        self.quotes = quotes or {}
        self.quote_requests = []

    async def get_open_positions(self):
        return self.positions

    async def fetch_crypto_quotes(self, symbols):
        self.quote_requests.append(list(symbols))
        return self.quotes


class _FailingPositionAlpaca(_FakeAlpaca):
    async def get_open_positions(self):
        raise RuntimeError("broker positions unavailable")


class _FakePriceService:
    def __init__(self, quotes):
        self.quotes = quotes
        self.requested = []

    async def get_quotes(self, symbols):
        self.requested.append(list(symbols))
        return self.quotes


def test_crypto_symbol_aliases_cover_broker_and_feed_forms():
    aliases = symbol_aliases("ETH/USD")

    assert "ETH/USD" in aliases
    assert "ETH-USD" in aliases
    assert "ETHUSD" in aliases
    assert "ETH" in aliases


@pytest.mark.asyncio
async def test_price_service_uses_yfinance_crypto_fallback_with_normalized_symbol():
    service = PriceService(coinmarketcap=_NoCmc(), alphavantage=_NoAv())
    called = []

    def fake_yfinance(canonical_symbol):
        called.append(canonical_symbol)
        return {"symbol": canonical_symbol, "price": 2345.67, "source": "yfinance"}

    service._fetch_yfinance_crypto_sync = fake_yfinance

    quotes = await service.get_quotes(["ETH/USD", "SOLUSD"])

    assert called == ["ETH/USD", "SOL/USD"]
    assert quotes["ETH/USD"]["price"] == pytest.approx(2345.67)
    assert quotes["SOLUSD"]["symbol"] == "SOLUSD"
    assert quotes["SOLUSD"]["source"] == "yfinance"


def test_mark_to_market_preserves_last_price_for_symbols_missing_from_partial_update():
    accountant = PortfolioAccountant("test", 1000.0)
    accountant.record_fill_direct("order-a", "AAPL", qty=1.0, fill_price=100.0)
    accountant.record_fill_direct("order-m", "MSFT", qty=1.0, fill_price=200.0)
    accountant.mark_to_market({"AAPL": 110.0, "MSFT": 210.0})

    accountant.mark_to_market({"AAPL": 111.0})

    positions = accountant.current_positions
    assert positions["AAPL"].current_price == pytest.approx(111.0)
    assert positions["MSFT"].current_price == pytest.approx(210.0)
    assert accountant._positions["MSFT"]["unrealised_pnl"] == pytest.approx(10.0)


@pytest.mark.asyncio
async def test_session_price_refresh_updates_crypto_from_quote_fallback_when_broker_key_differs():
    accountant = PortfolioAccountant("crypto", 1000.0)
    accountant.record_fill_direct("order-eth", "ETH/USD", qty=0.1, fill_price=2328.97)
    manager = SessionManager(
        alpaca_adapter=_FakeAlpaca({
            "ETHUSD": {
                "qty": 0.1,
                "side": "long",
                "entry_price": 2328.97,
                "current_price": 2328.97,
                "unrealized_pl": 0.0,
            }
        }),
        enable_news_adapters=False,
    )
    manager._pod_runtimes = {"crypto": _Runtime(accountant)}
    manager._price_service = _FakePriceService({
        "ETH/USD": {"symbol": "ETH/USD", "price": 2350.25, "source": "unit_quote"}
    })

    refresh = await manager._refresh_live_position_prices()

    snap = accountant.current_positions["ETH/USD"]
    assert refresh["updated_count"] == 1
    assert manager._price_service.requested == [["ETH/USD"]]
    assert snap.current_price == pytest.approx(2350.25)
    assert snap.unrealized_pnl == pytest.approx((2350.25 - 2328.97) * 0.1)
    assert snap.price_source == "unit_quote"
    assert snap.price_stale is False
    row = manager.get_all_positions()[0]
    assert row["entry_notional"] == pytest.approx(2328.97 * 0.1)
    assert row["current_notional"] == pytest.approx(2350.25 * 0.1)
    assert row["notional"] == pytest.approx(row["current_notional"])
    assert row["notional_basis"] == "current_price"


@pytest.mark.asyncio
async def test_session_price_refresh_updates_crypto_when_broker_positions_fail():
    accountant = PortfolioAccountant("crypto", 1000.0)
    accountant.record_fill_direct("order-sol", "SOL/USD", qty=2.0, fill_price=89.50)
    alpaca = _FailingPositionAlpaca(
        positions={},
        quotes={"SOL/USD": {"symbol": "SOL/USD", "price": 91.25, "source": "alpaca_crypto_snapshot"}},
    )
    manager = SessionManager(alpaca_adapter=alpaca, enable_news_adapters=False)
    manager._pod_runtimes = {"crypto": _Runtime(accountant)}

    refresh = await manager._refresh_live_position_prices()

    snap = accountant.current_positions["SOL/USD"]
    assert refresh["live_symbol_count"] == 0
    assert refresh["crypto_quote_count"] == 1
    assert alpaca.quote_requests == [["SOL/USD"]]
    assert snap.current_price == pytest.approx(91.25)
    assert snap.unrealized_pnl == pytest.approx((91.25 - 89.50) * 2.0)
    assert snap.price_source == "alpaca_crypto_snapshot"


@pytest.mark.asyncio
async def test_position_price_refresh_is_throttled_for_dashboard_callers():
    accountant = PortfolioAccountant("crypto", 1000.0)
    accountant.record_fill_direct("order-eth", "ETH/USD", qty=0.1, fill_price=2328.97)
    alpaca = _FakeAlpaca(
        positions={},
        quotes={"ETH/USD": {"symbol": "ETH/USD", "price": 2335.0, "source": "alpaca_crypto_snapshot"}},
    )
    manager = SessionManager(alpaca_adapter=alpaca, enable_news_adapters=False)
    manager._pod_runtimes = {"crypto": _Runtime(accountant)}

    first = await manager.refresh_live_position_prices_if_due()
    second = await manager.refresh_live_position_prices_if_due()

    assert first["updated_count"] == 1
    assert second["skipped"] is True
    assert second["reason"] == "recent"
    assert alpaca.quote_requests == [["ETH/USD"]]
