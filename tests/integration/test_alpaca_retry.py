"""Tests for AlpacaAdapter retry logic on transient errors."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
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
        assert mock_client.submit_order.call_count == 1

    @pytest.mark.asyncio
    async def test_exhausted_retries_returns_rejected(self, adapter):
        a, mock_client = adapter
        mock_client.submit_order.side_effect = ConnectionError("network down")

        result = await a.place_order("AAPL", 10, "buy", max_retries=2, timeout_seconds=1)
        assert result["status"] == "REJECTED"
        assert mock_client.submit_order.call_count == 2
