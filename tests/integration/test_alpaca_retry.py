"""Tests for AlpacaAdapter retry logic on transient errors."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from src.execution.paper.alpaca_adapter import AlpacaAdapter


@pytest.fixture
def adapter():
    """Create an AlpacaAdapter with mocked REST client."""
    with patch("src.execution.paper.alpaca_adapter.REST") as MockREST:
        mock_client = MagicMock()
        MockREST.return_value = mock_client
        with patch("src.execution.paper.alpaca_adapter.load_dotenv"):
            a = AlpacaAdapter(api_key="test-key", secret_key="test-secret")
        a._client = mock_client
        mock_client.get_asset.side_effect = lambda symbol: SimpleNamespace(
            symbol=symbol,
            asset_class="crypto" if "/" in symbol else "us_equity",
            status="active",
            tradable=True,
            fractionable=True,
            shortable=True,
        )
        mock_client.get_account.return_value = SimpleNamespace(
            buying_power="1000000",
            cash="1000000",
        )
        mock_client.get_position.side_effect = Exception("position not found")
        yield a, mock_client


class TestPlaceOrderRetry:

    @pytest.mark.asyncio
    async def test_succeeds_on_first_attempt(self, adapter):
        a, mock_client = adapter
        mock_order = MagicMock()
        mock_order.id = "ord-1"
        mock_order.symbol = "AAPL"
        mock_order.filled_qty = "10"
        mock_order.filled_avg_price = "150.00"
        mock_order.limit_price = None

        mock_client.submit_order.return_value = mock_order
        mock_client.get_order.return_value = mock_order

        result = await a.place_order("AAPL", 10, "buy", max_retries=3, timeout_seconds=1)
        assert result["status"] == "FILLED"
        assert mock_client.submit_order.call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_transient_error(self, adapter):
        a, mock_client = adapter
        mock_order = MagicMock()
        mock_order.id = "ord-1"
        mock_order.symbol = "AAPL"
        mock_order.filled_qty = "10"
        mock_order.filled_avg_price = "150.00"
        mock_order.limit_price = None

        mock_client.submit_order.side_effect = [
            ConnectionError("network timeout"),
            ConnectionError("network timeout"),
            mock_order,
        ]
        mock_client.get_order.return_value = mock_order

        result = await a.place_order("AAPL", 10, "buy", max_retries=3, timeout_seconds=1)
        assert result["status"] == "FILLED"
        assert mock_client.submit_order.call_count == 3

    @pytest.mark.asyncio
    async def test_no_retry_on_business_error(self, adapter):
        a, mock_client = adapter
        mock_client.submit_order.side_effect = Exception("insufficient buying power")

        result = await a.place_order("AAPL", 10, "buy", max_retries=3, timeout_seconds=1)
        assert result["status"] == "REJECTED"
        assert result["reason"] == "insufficient buying power"
        assert result["rejection_detail"] == "insufficient buying power"
        assert mock_client.submit_order.call_count == 1

    @pytest.mark.asyncio
    async def test_exhausted_retries_returns_rejected(self, adapter):
        a, mock_client = adapter
        mock_client.submit_order.side_effect = ConnectionError("network down")

        result = await a.place_order("AAPL", 10, "buy", max_retries=2, timeout_seconds=1)
        assert result["status"] == "REJECTED"
        assert result["reason"] == "network down"
        assert mock_client.submit_order.call_count == 2

    @pytest.mark.asyncio
    async def test_rejected_broker_status_preserves_reason(self, adapter):
        a, mock_client = adapter
        submitted = MagicMock()
        submitted.id = "ord-rej"
        submitted.symbol = "BTC/USD"
        submitted.filled_qty = "0"
        submitted.filled_avg_price = None

        rejected = MagicMock()
        rejected.id = "ord-rej"
        rejected.status = "rejected"
        rejected.filled_qty = "0"
        rejected.filled_avg_price = None
        rejected.reason = "time_in_force must be gtc or ioc for crypto"

        mock_client.submit_order.return_value = submitted
        mock_client.get_order.return_value = rejected

        result = await a.place_order("BTC/USD", 0.001, "buy", timeout_seconds=1)

        assert result["status"] == "REJECTED"
        assert result["order_id"] == "ord-rej"
        assert result["reason"] == "time_in_force must be gtc or ioc for crypto"
        assert result["broker_status"] == "REJECTED"

    @pytest.mark.asyncio
    async def test_crypto_orders_use_gtc_time_in_force(self, adapter):
        a, mock_client = adapter
        mock_order = MagicMock()
        mock_order.id = "ord-crypto"
        mock_order.symbol = "BTC/USD"
        mock_order.filled_qty = "0.001"
        mock_order.filled_avg_price = "70000"
        mock_order.limit_price = None

        mock_client.submit_order.return_value = mock_order
        mock_client.get_order.return_value = mock_order

        result = await a.place_order("BTC/USD", 0.001, "buy", timeout_seconds=1)

        assert result["status"] == "FILLED"
        assert mock_client.submit_order.call_args.kwargs["time_in_force"] == "gtc"


class TestBrokerPreflight:

    def test_clean_error_message_extracts_api_payload_message(self):
        response = SimpleNamespace(text='{"code":42210000,"message":"invalid crypto time_in_force"}')
        exc = Exception("Order rejected")
        exc.response = response

        assert AlpacaAdapter._clean_error_message(exc) == "invalid crypto time_in_force"

    @pytest.mark.asyncio
    async def test_unknown_asset_rejected_before_submit(self, adapter):
        a, mock_client = adapter
        mock_client.get_asset.side_effect = Exception("asset not found")

        result = await a.place_order("NOTREAL", 1, "buy", estimated_price=10)

        assert result["status"] == "REJECTED"
        assert result["stage"] == "preflight"
        assert result["reason_code"] == "asset_lookup_failed"
        assert "asset not found" in result["reason"]
        mock_client.submit_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_tradable_asset_rejected_before_submit(self, adapter):
        a, mock_client = adapter
        mock_client.get_asset.return_value = SimpleNamespace(
            symbol="AAPL",
            asset_class="us_equity",
            status="active",
            tradable=False,
            fractionable=True,
            shortable=True,
        )
        mock_client.get_asset.side_effect = None

        result = await a.place_order("AAPL", 1, "buy", estimated_price=100)

        assert result["status"] == "REJECTED"
        assert result["stage"] == "preflight"
        assert result["reason_code"] == "asset_not_tradable"
        mock_client.submit_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_buying_power_rejected_before_submit(self, adapter):
        a, mock_client = adapter
        mock_client.get_account.return_value = SimpleNamespace(
            buying_power="50",
            cash="50",
        )

        result = await a.place_order("AAPL", 2, "buy", estimated_price=100)

        assert result["status"] == "REJECTED"
        assert result["stage"] == "preflight"
        assert result["reason_code"] == "insufficient_buying_power"
        mock_client.submit_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_asset_capability_cache_reuses_lookup(self, adapter):
        a, mock_client = adapter
        mock_order = MagicMock()
        mock_order.id = "ord-cache"
        mock_order.symbol = "AAPL"
        mock_order.filled_qty = "1"
        mock_order.filled_avg_price = "100"
        mock_order.limit_price = None
        mock_client.submit_order.return_value = mock_order
        mock_client.get_order.return_value = mock_order

        first = await a.place_order("AAPL", 1, "buy", estimated_price=100, timeout_seconds=1)
        second = await a.place_order("AAPL", 1, "buy", estimated_price=100, timeout_seconds=1)

        assert first["status"] == "FILLED"
        assert second["status"] == "FILLED"
        assert mock_client.get_asset.call_count == 1


class TestCryptoMarketData:

    @pytest.mark.asyncio
    async def test_fetch_crypto_quotes_uses_snapshot_trade_prices(self, adapter):
        a, mock_client = adapter
        mock_client.get_crypto_snapshots.return_value = {
            "ETH/USD": SimpleNamespace(
                latest_trade=SimpleNamespace(price="2292.30"),
                latest_quote=None,
                minute_bar=None,
                daily_bar=None,
                prev_daily_bar=None,
            ),
            "SOL/USD": SimpleNamespace(
                latest_trade=SimpleNamespace(price="88.7521"),
                latest_quote=None,
                minute_bar=None,
                daily_bar=None,
                prev_daily_bar=None,
            ),
        }

        quotes = await a.fetch_crypto_quotes(["ETH/USD", "SOL/USD"])

        assert quotes["ETH/USD"]["price"] == pytest.approx(2292.30)
        assert quotes["ETH/USD"]["source"] == "alpaca_crypto_snapshot"
        assert quotes["SOL/USD"]["price"] == pytest.approx(88.7521)
        mock_client.get_crypto_snapshots.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_crypto_quotes_falls_back_to_latest_trade(self, adapter):
        a, mock_client = adapter
        mock_client.get_crypto_snapshots.return_value = {}
        mock_client.get_latest_crypto_trades.return_value = {
            "ETH/USD": SimpleNamespace(price="2291.10"),
        }

        quotes = await a.fetch_crypto_quotes(["ETH/USD"])

        assert quotes["ETH/USD"]["price"] == pytest.approx(2291.10)
        assert quotes["ETH/USD"]["source"] == "alpaca_crypto_trade"
