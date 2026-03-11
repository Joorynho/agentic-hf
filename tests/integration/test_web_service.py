"""Integration tests for FastAPI web service (Phase 2.1).

Tests REST endpoints, WebSocket connections, and EventBus integration.
"""

import pytest
import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

from fastapi.testclient import TestClient
from websockets.client import connect as ws_connect

from src.web.server import create_app, ConnectionManager, EventBusListener
from src.core.bus.event_bus import EventBus
from src.core.bus.audit_log import AuditLog
from src.core.models.messages import AgentMessage
from src.core.models.pod_summary import PodSummary, PodRiskMetrics, PodExposureBucket
from src.core.models.enums import PodStatus


@pytest.fixture
def event_bus():
    """Create an EventBus for testing."""
    return EventBus(audit_log=AuditLog())


@pytest.fixture
def app(event_bus):
    """Create a test FastAPI app."""
    return create_app(event_bus=event_bus, session_start_time=datetime.now(timezone.utc))


@pytest.fixture
def client(app):
    """Create a test client."""
    return TestClient(app)


class TestConnectionManager:
    """Test WebSocket ConnectionManager."""

    @pytest.mark.asyncio
    async def test_connect_and_disconnect(self):
        """Test connecting and disconnecting a WebSocket."""
        manager = ConnectionManager()

        # Mock WebSocket
        ws = AsyncMock()

        # Connect
        await manager.connect(ws)
        assert ws in manager.active_connections
        assert len(manager.active_connections) == 1

        # Disconnect
        await manager.disconnect(ws)
        assert ws not in manager.active_connections
        assert len(manager.active_connections) == 0

    @pytest.mark.asyncio
    async def test_broadcast_to_all_clients(self):
        """Test broadcasting a message to all connected clients."""
        manager = ConnectionManager()

        # Mock WebSockets
        ws1 = AsyncMock()
        ws2 = AsyncMock()

        # Connect
        await manager.connect(ws1)
        await manager.connect(ws2)

        # Broadcast
        message = {"type": "test", "data": "hello"}
        await manager.broadcast(message)

        # Verify both clients received the message
        ws1.send_json.assert_called_once_with(message)
        ws2.send_json.assert_called_once_with(message)

    @pytest.mark.asyncio
    async def test_broadcast_handles_failed_connection(self):
        """Test that broadcast handles disconnected clients gracefully."""
        manager = ConnectionManager()

        ws1 = AsyncMock()
        ws2 = AsyncMock()

        # ws2 will throw an error on send
        ws2.send_json.side_effect = Exception("Connection closed")

        await manager.connect(ws1)
        await manager.connect(ws2)

        # Broadcast should not raise even though ws2 fails
        message = {"type": "test", "data": "hello"}
        await manager.broadcast(message)

        ws1.send_json.assert_called_once_with(message)
        ws2.send_json.assert_called_once_with(message)


class TestEventBusListener:
    """Test EventBusListener integration."""

    @pytest.mark.asyncio
    async def test_subscribe_to_topics(self, event_bus):
        """Test subscribing to EventBus topics."""
        manager = ConnectionManager()
        listener = EventBusListener(event_bus, manager)

        # Subscribe should succeed
        await listener.subscribe()
        assert listener._subscribed

    @pytest.mark.asyncio
    async def test_broadcast_pod_update(self, event_bus):
        """Test broadcasting a pod update from EventBus."""
        manager = ConnectionManager()
        listener = EventBusListener(event_bus, manager)

        # Mock WebSocket
        ws = AsyncMock()
        await manager.connect(ws)

        # Create and publish a pod summary message
        summary_dict = {
            "pod_id": "alpha",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "ACTIVE",
            "risk_metrics": {
                "pod_id": "alpha",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "nav": 105.0,
                "daily_pnl": 5.0,
                "drawdown_from_hwm": 0.0,
                "current_vol_ann": 0.10,
                "gross_leverage": 1.0,
                "net_leverage": 1.0,
                "var_95_1d": 0.02,
                "es_95_1d": 0.03,
            },
            "exposure_buckets": [],
            "expected_return_estimate": 0.05,
            "turnover_daily_pct": 0.10,
            "heartbeat_ok": True,
        }

        msg = AgentMessage(
            timestamp=datetime.now(timezone.utc),
            sender="pod.alpha",
            recipient="*",
            topic="pod.alpha.gateway",
            payload=summary_dict,
        )

        # Manually call the handler
        await listener._on_pod_update(msg)

        # Verify WebSocket received broadcast
        ws.send_json.assert_called_once()
        call_args = ws.send_json.call_args
        broadcast_msg = call_args[0][0]
        assert broadcast_msg["type"] == "pod_summary"
        assert broadcast_msg["pod_id"] == "alpha"

    @pytest.mark.asyncio
    async def test_broadcast_governance_event(self, event_bus):
        """Test broadcasting a governance event from EventBus."""
        manager = ConnectionManager()
        listener = EventBusListener(event_bus, manager)

        ws = AsyncMock()
        await manager.connect(ws)

        msg = AgentMessage(
            timestamp=datetime.now(timezone.utc),
            sender="ceo",
            recipient="*",
            topic="governance.ceo",
            payload={"action": "check_drift", "pod_id": "alpha"},
        )

        await listener._on_governance(msg)

        ws.send_json.assert_called_once()
        broadcast_msg = ws.send_json.call_args[0][0]
        assert broadcast_msg["type"] == "governance"


class TestRESTEndpoints:
    """Test REST API endpoints."""

    def test_health_check(self, client):
        """Test health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "timestamp" in data

    def test_get_session_info(self, client):
        """Test get session info endpoint."""
        response = client.get("/api/session")
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "live-session-1"
        assert data["num_pods"] == 4
        assert data["capital_per_pod"] == 0.0
        assert "iteration" in data
        assert "uptime_seconds" in data

    def test_get_all_pods_empty(self, client):
        """Test get all pods endpoint when no pods exist."""
        response = client.get("/api/pods")
        assert response.status_code == 200
        data = response.json()
        assert data["pods"] == []
        assert data["count"] == 0

    def test_get_all_pods_with_data(self, client, app):
        """Test get all pods endpoint with pod data."""
        # Inject pod summaries into app state
        app.state.pod_summaries = {
            "alpha": {
                "pod_id": "alpha",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "ACTIVE",
                "risk_metrics": {
                    "nav": 105.0,
                    "daily_pnl": 5.0,
                },
            },
            "fx": {
                "pod_id": "fx",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "ACTIVE",
                "risk_metrics": {
                    "nav": 102.0,
                    "daily_pnl": 2.0,
                },
            },
        }

        response = client.get("/api/pods")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert len(data["pods"]) == 2

        # Check pod data
        pods = {p["pod_id"]: p for p in data["pods"]}
        assert pods["alpha"]["nav"] == 105.0
        assert pods["fx"]["nav"] == 102.0

    def test_get_pod_detail(self, client, app):
        """Test get individual pod detail endpoint."""
        # Inject pod summary
        app.state.pod_summaries = {
            "alpha": {
                "pod_id": "alpha",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "ACTIVE",
                "risk_metrics": {"nav": 105.0},
            },
        }

        response = client.get("/api/pods/alpha")
        assert response.status_code == 200
        data = response.json()
        assert data["pod_id"] == "alpha"
        assert data["data"]["risk_metrics"]["nav"] == 105.0

    def test_get_pod_detail_not_found(self, client):
        """Test get pod detail when pod does not exist."""
        response = client.get("/api/pods/nonexistent")
        assert response.status_code == 404

    def test_get_risk_status(self, client):
        """Test get risk status endpoint."""
        response = client.get("/api/risk")
        assert response.status_code == 200
        data = response.json()
        assert "risk_halt" in data
        assert "risk_halt_reason" in data
        assert "breached_pods" in data

    def test_get_risk_status_with_halt(self, client, app):
        """Test get risk status when risk halt is active."""
        app.state.risk_halt = True
        app.state.risk_halt_reason = "VAR breach in pod alpha"

        response = client.get("/api/risk")
        assert response.status_code == 200
        data = response.json()
        assert data["risk_halt"] is True
        assert data["risk_halt_reason"] == "VAR breach in pod alpha"

    def test_get_audit_log(self, client):
        """Test get audit log endpoint."""
        response = client.get("/api/audit")
        assert response.status_code == 200
        data = response.json()
        assert "entries" in data
        assert "count" in data


class TestWebSocketIntegration:
    """Test WebSocket functionality."""

    def test_websocket_connect(self, app):
        """Test WebSocket connection using TestClient."""
        client = TestClient(app)
        with client.websocket_connect("/ws") as websocket:
            # Send a test message
            websocket.send_text("ping")
            # Connection should remain open
            assert websocket is not None

    def test_websocket_multiple_clients(self, app):
        """Test multiple WebSocket clients connected."""
        client1 = TestClient(app)
        client2 = TestClient(app)

        with client1.websocket_connect("/ws") as ws1:
            with client2.websocket_connect("/ws") as ws2:
                # Both connections should be active
                manager = app.state.connection_manager
                assert len(manager.active_connections) == 2


class TestAppStateManagement:
    """Test app state update mechanism."""

    @pytest.mark.asyncio
    async def test_update_session_state(self, app):
        """Test updating session state."""
        pod_summaries = {
            "alpha": {
                "pod_id": "alpha",
                "nav": 105.0,
                "status": "ACTIVE",
            },
        }

        await app.state.update_session_state(
            iteration=10,
            capital_per_pod=100.0,
            pod_summaries=pod_summaries,
            risk_halt=False,
        )

        assert app.state.iteration == 10
        assert app.state.capital_per_pod == 100.0
        assert app.state.pod_summaries == pod_summaries
        assert app.state.risk_halt is False

    @pytest.mark.asyncio
    async def test_update_session_state_with_risk_halt(self, app):
        """Test updating session state with risk halt."""
        await app.state.update_session_state(
            iteration=5,
            capital_per_pod=100.0,
            pod_summaries={},
            risk_halt=True,
            risk_halt_reason="Critical risk breach",
        )

        assert app.state.risk_halt is True
        assert app.state.risk_halt_reason == "Critical risk breach"


class TestEndToEnd:
    """End-to-end integration tests."""

    def test_session_info_reflects_state(self, client, app):
        """Test that session info endpoint reflects app state."""
        # Update app state
        app.state.capital_per_pod = 50.0
        app.state.iteration = 25

        response = client.get("/api/session")
        assert response.status_code == 200
        data = response.json()
        assert data["capital_per_pod"] == 50.0
        assert data["iteration"] == 25
        assert data["total_capital"] == 50.0 * 4  # 4 pods

    def test_pods_endpoint_reflects_summaries(self, client, app):
        """Test that pods endpoint reflects app state."""
        # Create a realistic pod summary
        now = datetime.now(timezone.utc)
        app.state.pod_summaries = {
            "alpha": {
                "pod_id": "alpha",
                "timestamp": now.isoformat(),
                "status": "ACTIVE",
                "risk_metrics": {
                    "nav": 110.0,
                    "daily_pnl": 10.0,
                    "drawdown_from_hwm": 0.02,
                    "current_vol_ann": 0.15,
                    "gross_leverage": 1.2,
                    "net_leverage": 1.0,
                    "var_95_1d": 0.025,
                    "es_95_1d": 0.035,
                },
                "exposure_buckets": [],
                "expected_return_estimate": 0.08,
                "turnover_daily_pct": 0.12,
                "heartbeat_ok": True,
            },
        }

        response = client.get("/api/pods")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["pods"][0]["nav"] == 110.0
        assert data["pods"][0]["pod_id"] == "alpha"

    @pytest.mark.asyncio
    async def test_full_flow_state_update_and_endpoints(self, app, event_bus):
        """Test full flow: update state, then check endpoints."""
        # Create realistic pod summaries
        pod_summaries = {
            "alpha": {
                "pod_id": "alpha",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "ACTIVE",
                "risk_metrics": {
                    "nav": 105.0,
                    "daily_pnl": 5.0,
                },
            },
        }

        # Update state
        await app.state.update_session_state(
            iteration=100,
            capital_per_pod=100.0,
            pod_summaries=pod_summaries,
            risk_halt=False,
        )

        # Verify state
        assert app.state.iteration == 100
        assert len(app.state.pod_summaries) == 1

        # Use TestClient to verify endpoints
        client = TestClient(app)

        # Check session endpoint
        resp = client.get("/api/session")
        assert resp.status_code == 200
        assert resp.json()["iteration"] == 100

        # Check pods endpoint
        resp = client.get("/api/pods")
        assert resp.status_code == 200
        assert resp.json()["count"] == 1


class TestSessionControl:
    """Tests for session start/stop control endpoints."""

    @pytest.fixture
    def mock_session_manager(self):
        """Create a mock SessionManager with required properties."""
        sm = MagicMock()
        sm.session_active = False
        sm.iteration = 0
        sm._pod_runtimes = {}
        sm.stop_session = AsyncMock()
        sm.start_live_session = AsyncMock()
        sm.run_event_loop = AsyncMock()
        return sm

    @pytest.fixture
    def app_with_manager(self, event_bus, mock_session_manager):
        """Create a test app with a mock SessionManager."""
        return create_app(
            event_bus=event_bus,
            session_start_time=datetime.now(timezone.utc),
            session_manager=mock_session_manager,
        )

    @pytest.fixture
    def client_with_manager(self, app_with_manager):
        return TestClient(app_with_manager)

    def test_session_status_idle(self, client_with_manager):
        """GET /api/session/status returns idle when no session is running."""
        resp = client_with_manager.get("/api/session/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["active"] is False
        assert "iteration" in data
        assert "uptime_seconds" in data
        assert "pod_count" in data

    def test_session_status_active(self, app_with_manager, client_with_manager):
        """GET /api/session/status returns active when session is running."""
        sm = app_with_manager.state.session_manager
        sm.session_active = True
        sm.iteration = 42
        sm._pod_runtimes = {"equities": None, "fx": None, "crypto": None, "commodities": None}

        resp = client_with_manager.get("/api/session/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["active"] is True
        assert data["iteration"] == 42
        assert data["pod_count"] == 4

    def test_stop_session_calls_manager(self, app_with_manager, client_with_manager):
        """POST /api/session/stop calls stop_session on the manager."""
        sm = app_with_manager.state.session_manager
        sm.session_active = True

        resp = client_with_manager.post("/api/session/stop")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        sm.stop_session.assert_called_once()

    def test_stop_session_when_idle(self, client_with_manager):
        """POST /api/session/stop returns error when session is already idle."""
        resp = client_with_manager.post("/api/session/stop")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert "not running" in data["detail"].lower()

    def test_start_session_when_idle(self, app_with_manager, client_with_manager):
        """POST /api/session/start spawns session when idle."""
        sm = app_with_manager.state.session_manager
        sm.session_active = False

        resp = client_with_manager.post("/api/session/start")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "starting" in data["detail"].lower()

    def test_start_session_when_already_active(self, app_with_manager, client_with_manager):
        """POST /api/session/start returns error when already running."""
        sm = app_with_manager.state.session_manager
        sm.session_active = True

        resp = client_with_manager.post("/api/session/start")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert "already running" in data["detail"].lower()

    def test_session_status_no_manager(self, event_bus):
        """GET /api/session/status still works without a manager (returns idle)."""
        app = create_app(event_bus=event_bus)
        client = TestClient(app)
        resp = client.get("/api/session/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["active"] is False

    def test_stop_without_manager_returns_503(self, event_bus):
        """POST /api/session/stop returns 503 without a manager."""
        app = create_app(event_bus=event_bus)
        client = TestClient(app)
        resp = client.post("/api/session/stop")
        assert resp.status_code == 503

    def test_start_without_manager_returns_503(self, event_bus):
        """POST /api/session/start returns 503 without a manager."""
        app = create_app(event_bus=event_bus)
        client = TestClient(app)
        resp = client.post("/api/session/start")
        assert resp.status_code == 503
