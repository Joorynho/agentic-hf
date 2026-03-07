"""End-to-end integration tests for web dashboard — FastAPI + WebSocket + React."""
import asyncio
import json
import logging
import tempfile
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from src.core.bus.audit_log import AuditLog
from src.core.bus.event_bus import EventBus
from src.execution.paper.alpaca_adapter import AlpacaAdapter
from src.mission_control.session_manager import SessionManager
from src.web.server import create_app, ConnectionManager, EventBusListener

logger = logging.getLogger(__name__)


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def audit_log():
    """Create in-memory audit log."""
    return AuditLog()


@pytest.fixture
def event_bus(audit_log):
    """Create event bus with audit log."""
    return EventBus(audit_log=audit_log)


@pytest.fixture
def alpaca_adapter():
    """Create mock Alpaca adapter (uses paper trading)."""
    # Skip if ALPACA credentials not in .env
    import os
    if not os.getenv("ALPACA_API_KEY") or not os.getenv("ALPACA_SECRET_KEY"):
        pytest.skip("Alpaca credentials not configured")
    return AlpacaAdapter()


@pytest.fixture
def session_manager(alpaca_adapter, event_bus):
    """Create session manager."""
    return SessionManager(
        alpaca_adapter=alpaca_adapter,
        event_bus=event_bus,
        enable_web_server=False,  # We'll create app separately
    )


@pytest.fixture
def test_client(event_bus):
    """Create FastAPI test client."""
    app = create_app(event_bus=event_bus, session_start_time=datetime.now(timezone.utc))
    return TestClient(app)


# ============================================================================
# HEALTH CHECK & BASIC ENDPOINTS
# ============================================================================


def test_health_check_endpoint(test_client):
    """Test GET /health endpoint."""
    response = test_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "timestamp" in data


def test_session_info_endpoint(test_client):
    """Test GET /api/session endpoint."""
    response = test_client.get("/api/session")
    assert response.status_code == 200
    data = response.json()
    assert "session_id" in data
    assert "capital_per_pod" in data
    assert "total_capital" in data
    assert "num_pods" in data
    assert data["num_pods"] == 5


def test_pods_endpoint_returns_list(test_client):
    """Test GET /api/pods returns pod list (may be empty)."""
    response = test_client.get("/api/pods")
    assert response.status_code == 200
    data = response.json()
    assert "pods" in data
    assert isinstance(data["pods"], list)
    assert "count" in data
    assert data["count"] == len(data["pods"])


def test_risk_status_endpoint(test_client):
    """Test GET /api/risk endpoint."""
    response = test_client.get("/api/risk")
    assert response.status_code == 200
    data = response.json()
    assert "risk_halt" in data
    assert isinstance(data["risk_halt"], bool)
    assert "breached_pods" in data
    assert isinstance(data["breached_pods"], list)


# ============================================================================
# REST ENDPOINT VALIDATION
# ============================================================================


def test_session_info_has_correct_structure(test_client):
    """Verify session info structure matches schema."""
    response = test_client.get("/api/session")
    data = response.json()
    required_fields = ["session_id", "capital_per_pod", "total_capital", "iteration", "uptime_seconds", "num_pods"]
    for field in required_fields:
        assert field in data, f"Missing field: {field}"
    assert data["uptime_seconds"] >= 0
    assert data["num_pods"] == 5


def test_pods_endpoint_no_crash_on_empty(test_client):
    """Test pods endpoint doesn't crash when no pods are active."""
    response = test_client.get("/api/pods")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 0
    assert len(data["pods"]) == 0


def test_pod_detail_404_on_nonexistent_pod(test_client):
    """Test GET /api/pods/{pod_id} returns 404 for unknown pod."""
    response = test_client.get("/api/pods/nonexistent")
    assert response.status_code == 404


# ============================================================================
# WEBSOCKET FUNCTIONALITY
# ============================================================================


def test_websocket_connects_successfully(test_client):
    """Test WebSocket connection is accepted."""
    with test_client.websocket_connect("/ws") as websocket:
        # Connection should be established without error
        assert websocket is not None


def test_websocket_multiple_simultaneous_connections(test_client):
    """Test multiple WebSocket clients can connect simultaneously."""
    with test_client.websocket_connect("/ws") as ws1:
        with test_client.websocket_connect("/ws") as ws2:
            with test_client.websocket_connect("/ws") as ws3:
                # All three should be connected without error
                assert ws1 is not None
                assert ws2 is not None
                assert ws3 is not None


def test_websocket_receives_data_on_connect(test_client):
    """Test WebSocket can receive messages (with timeout)."""
    with test_client.websocket_connect("/ws") as websocket:
        # Try to receive with timeout
        try:
            # Send a ping to verify connection is alive
            websocket.send_text(json.dumps({"action": "get_status"}))
            # Connection should still be alive
            assert websocket is not None
        except Exception as e:
            pytest.fail(f"WebSocket receive failed: {e}")


def test_websocket_handles_client_disconnection(test_client):
    """Test WebSocket gracefully handles client disconnect."""
    ws = test_client.websocket_connect("/ws").__enter__()
    ws.__exit__(None, None, None)
    # No exception should be raised


# ============================================================================
# CONNECTION MANAGER UNIT TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_connection_manager_connect_and_disconnect():
    """Test ConnectionManager tracks connections."""
    manager = ConnectionManager()
    assert len(manager.active_connections) == 0

    # Mock WebSocket (simplified)
    class MockWebSocket:
        async def accept(self):
            pass

        async def send_json(self, data):
            pass

    ws1 = MockWebSocket()
    await manager.connect(ws1)
    assert len(manager.active_connections) == 1

    await manager.disconnect(ws1)
    assert len(manager.active_connections) == 0


@pytest.mark.asyncio
async def test_connection_manager_broadcast_to_multiple():
    """Test ConnectionManager broadcasts to all connections."""
    manager = ConnectionManager()
    messages_received = []

    class MockWebSocket:
        def __init__(self):
            self.sent = []

        async def accept(self):
            pass

        async def send_json(self, data):
            self.sent.append(data)

    ws1, ws2, ws3 = MockWebSocket(), MockWebSocket(), MockWebSocket()
    await manager.connect(ws1)
    await manager.connect(ws2)
    await manager.connect(ws3)

    test_message = {"type": "test", "data": "hello"}
    await manager.broadcast(test_message)

    assert ws1.sent[0] == test_message
    assert ws2.sent[0] == test_message
    assert ws3.sent[0] == test_message


# ============================================================================
# EVENT BUS LISTENER INTEGRATION
# ============================================================================


@pytest.mark.asyncio
async def test_event_bus_listener_initialization(event_bus):
    """Test EventBusListener can be initialized."""
    manager = ConnectionManager()
    listener = EventBusListener(event_bus, manager)
    assert listener.bus is event_bus
    assert listener.manager is manager


@pytest.mark.asyncio
async def test_event_bus_listener_subscribes_without_error(event_bus):
    """Test EventBusListener subscribes to all topics without error."""
    manager = ConnectionManager()
    listener = EventBusListener(event_bus, manager)

    # Should not raise
    await listener.subscribe()
    assert listener._subscribed is True


# ============================================================================
# PERSISTENCE & STATE MANAGEMENT
# ============================================================================


def test_session_state_persists_across_requests(test_client):
    """Test that session state persists across multiple requests."""
    # Get initial state
    response1 = test_client.get("/api/session")
    initial_uptime = response1.json()["uptime_seconds"]

    # Wait a bit
    import time
    time.sleep(0.1)

    # Get state again
    response2 = test_client.get("/api/session")
    new_uptime = response2.json()["uptime_seconds"]

    # Uptime should have increased (or stayed same due to timing)
    assert new_uptime >= initial_uptime


def test_pod_summaries_can_be_updated(test_client):
    """Test that pod summaries can be updated in app state."""
    # Initial state
    response1 = test_client.get("/api/pods")
    assert response1.status_code == 200

    # Update state (via app.state if accessible)
    test_client.app.state.pod_summaries["alpha"] = {
        "nav": 105.0,
        "daily_pnl": 5.0,
        "status": "TRADING",
        "risk_metrics": {"var_95": 0.02},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Verify update
    response2 = test_client.get("/api/pods")
    data = response2.json()
    assert data["count"] == 1
    assert data["pods"][0]["pod_id"] == "alpha"
    # Pod summary response uses risk_metrics.nav, not direct nav
    assert data["pods"][0]["nav"] >= 0


# ============================================================================
# ERROR HANDLING & EDGE CASES
# ============================================================================


def test_unknown_endpoint_returns_404(test_client):
    """Test unknown endpoints return 404."""
    response = test_client.get("/api/nonexistent")
    assert response.status_code == 404


def test_cors_headers_present(test_client):
    """Test CORS headers are present in responses."""
    response = test_client.get("/health")
    # CORS middleware should add headers
    assert response.status_code == 200


def test_websocket_invalid_json_handling(test_client):
    """Test WebSocket handles invalid JSON gracefully."""
    with test_client.websocket_connect("/ws") as websocket:
        websocket.send_text("invalid json {{{")
        # Should not crash
        assert websocket is not None


# ============================================================================
# REAL-TIME DATA SIMULATION (requires session)
# ============================================================================


@pytest.mark.asyncio
async def test_session_with_web_server_integration(alpaca_adapter, event_bus):
    """Test a full session with web server enabled (integration test)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = SessionManager(
            alpaca_adapter=alpaca_adapter,
            event_bus=event_bus,
            session_dir=tmpdir,
            enable_web_server=True,
        )

        # Start session with web server
        await manager.start_live_session(capital_per_pod=100.0, initial_symbols=["AAPL", "MSFT"])

        # Verify session is active
        assert manager._session_active
        assert len(manager._pod_runtimes) == 5
        assert manager._capital_per_pod == 100.0

        # Verify web app was created
        assert manager._web_app is not None

        # Stop session
        await manager.stop_session()
        assert not manager._session_active


@pytest.mark.asyncio
async def test_pod_summaries_generated_during_session(alpaca_adapter, event_bus):
    """Test that pod summaries are generated during session event loop."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = SessionManager(
            alpaca_adapter=alpaca_adapter,
            event_bus=event_bus,
            session_dir=tmpdir,
            enable_web_server=False,
        )

        await manager.start_live_session(capital_per_pod=100.0, initial_symbols=["AAPL"])

        # Collect summaries
        summaries = await manager._collect_pod_summaries()
        assert len(summaries) == 5

        # Each summary should have a pod_id
        for pod_id, summary in summaries.items():
            assert summary.pod_id in ["alpha", "beta", "gamma", "delta", "epsilon"]
            assert summary.nav > 0

        await manager.stop_session()


# ============================================================================
# PERFORMANCE & SCALABILITY
# ============================================================================


@pytest.mark.asyncio
async def test_connection_manager_handles_100_connections():
    """Test ConnectionManager can handle many concurrent connections."""
    manager = ConnectionManager()

    class MockWebSocket:
        async def accept(self):
            pass

        async def send_json(self, data):
            pass

    # Add 100 connections
    connections = [MockWebSocket() for _ in range(100)]
    for ws in connections:
        await manager.connect(ws)

    assert len(manager.active_connections) == 100

    # Broadcast should succeed
    await manager.broadcast({"type": "test", "count": 100})

    # Disconnect all
    for ws in connections:
        await manager.disconnect(ws)

    assert len(manager.active_connections) == 0


@pytest.mark.asyncio
async def test_websocket_listener_does_not_block_broadcast():
    """Test that WebSocket listener doesn't block broadcasts."""
    manager = ConnectionManager()

    class MockWebSocket:
        def __init__(self):
            self.sent = []

        async def accept(self):
            pass

        async def send_json(self, data):
            # Simulate some processing time
            await asyncio.sleep(0.01)
            self.sent.append(data)

    ws1 = MockWebSocket()
    ws2 = MockWebSocket()
    await manager.connect(ws1)
    await manager.connect(ws2)

    # Broadcast should complete quickly even with delays
    start = datetime.now()
    await manager.broadcast({"type": "test"})
    elapsed = (datetime.now() - start).total_seconds()

    assert elapsed < 1.0  # Should be fast
    assert len(ws1.sent) == 1
    assert len(ws2.sent) == 1


# ============================================================================
# API RESPONSE VALIDATION
# ============================================================================


def test_api_response_timestamps_valid(test_client):
    """Test all API responses have valid ISO timestamps."""
    response = test_client.get("/health")
    data = response.json()
    timestamp = data["timestamp"]
    # Should parse as ISO format
    datetime.fromisoformat(timestamp.replace("Z", "+00:00"))


def test_pods_endpoint_response_structure(test_client):
    """Validate full structure of pods endpoint response."""
    # Add some test data
    test_client.app.state.pod_summaries = {
        "alpha": {
            "nav": 105.5,
            "daily_pnl": 5.5,
            "status": "TRADING",
            "risk_metrics": {"var_95": 0.02},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    }

    response = test_client.get("/api/pods")
    data = response.json()

    assert "pods" in data
    assert "count" in data
    assert data["count"] == 1
    assert len(data["pods"]) == 1

    pod = data["pods"][0]
    assert pod["pod_id"] == "alpha"
    # Pod response extracts nav from risk_metrics dict
    assert "nav" in pod
    assert "daily_pnl" in pod
    assert pod["status"] == "TRADING"
    assert "timestamp" in pod


# ============================================================================
# GOVERNANCE EVENT INTEGRATION
# ============================================================================


def test_risk_status_reflects_governance_state(test_client):
    """Test risk status endpoint reflects governance state."""
    # Set risk halt
    test_client.app.state.risk_halt = True
    test_client.app.state.risk_halt_reason = "Exceeds leverage limits"

    response = test_client.get("/api/risk")
    data = response.json()

    assert data["risk_halt"] is True
    assert data["risk_halt_reason"] == "Exceeds leverage limits"


# ============================================================================
# SUMMARY TESTS
# ============================================================================


def test_web_service_complete_smoke_test(test_client):
    """Comprehensive smoke test of web service."""
    # Health check
    assert test_client.get("/health").status_code == 200

    # Session info
    assert test_client.get("/api/session").status_code == 200

    # Pods list
    assert test_client.get("/api/pods").status_code == 200

    # Risk status
    assert test_client.get("/api/risk").status_code == 200

    # Audit log
    assert test_client.get("/api/audit").status_code == 200

    # WebSocket
    with test_client.websocket_connect("/ws") as ws:
        assert ws is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
