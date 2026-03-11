from unittest.mock import AsyncMock

import pytest

from src.core.bus.event_bus import EventBus
from src.data.adapters.polymarket_adapter import PolymarketAdapter
from src.execution.paper.alpaca_adapter import AlpacaAdapter
from src.mission_control.session_manager import SessionManager


@pytest.mark.asyncio
async def test_session_manager_injects_polymarket_into_researchers():
    """SessionManager creates all 4 pods with PolymarketAdapter in each researcher."""
    bus = EventBus()
    mock_alpaca = AsyncMock(spec=AlpacaAdapter)
    mock_alpaca.fetch_account = AsyncMock(
        return_value={"equity": 10000.0, "buying_power": 5000.0, "position_count": 0}
    )
    mock_alpaca.fetch_bars = AsyncMock(
        side_effect=lambda symbols, **kw: {s: [] for s in (symbols or [])}
    )

    manager = SessionManager(event_bus=bus, alpaca_adapter=mock_alpaca)
    await manager.start_live_session()

    # All 4 pods (equities, fx, crypto, commodities) get PolymarketAdapter
    for pod_id in ["equities", "fx", "crypto", "commodities"]:
        researcher = manager._pod_runtimes[pod_id]._researcher
        assert researcher.polymarket_adapter is not None
        assert isinstance(researcher.polymarket_adapter, PolymarketAdapter)
