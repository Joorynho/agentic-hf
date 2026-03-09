import pytest
from src.mission_control.session_manager import SessionManager
from src.core.bus.event_bus import EventBus
from src.data.adapters.polymarket_adapter import PolymarketAdapter


@pytest.mark.asyncio
async def test_session_manager_injects_polymarket_into_gamma():
    """SessionManager creates Gamma pod with PolymarketAdapter."""
    bus = EventBus()
    manager = SessionManager(event_bus=bus)

    # Call initialization (builds all 5 pods)
    await manager.start_live_session()

    # Verify Gamma pod's researcher has adapter
    gamma_pod = manager._pod_runtimes["gamma"]
    gamma_researcher = gamma_pod._researcher

    assert gamma_researcher.polymarket_adapter is not None
    assert isinstance(gamma_researcher.polymarket_adapter, PolymarketAdapter)
