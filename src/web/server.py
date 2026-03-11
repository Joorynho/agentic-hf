"""FastAPI web service for Agentic HF Mission Control.

Provides REST API and WebSocket real-time data bridge to SessionManager EventBus.
- REST endpoints: session info, pod summaries, governance state, audit log
- WebSocket: real-time broadcasting of pod updates, trades, governance events
- EventBus integration: subscribes to all major topics and broadcasts to clients
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Load .env file at module import time
_env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(str(_env_path))

from src.core.bus.event_bus import EventBus
from src.core.models.messages import AgentMessage
from src.core.models.pod_summary import PodSummary

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections and broadcasts messages."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket):
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)
        logger.info("[web] WebSocket connected, total=%d", len(self.active_connections))

    async def disconnect(self, websocket: WebSocket):
        """Unregister a WebSocket connection."""
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
        logger.info("[web] WebSocket disconnected, total=%d", len(self.active_connections))

    async def broadcast(self, message: dict):
        """Broadcast a message to all connected clients.

        Args:
            message: Dict with 'type' and 'data' keys
        """
        if not self.active_connections:
            return

        # Create a copy of active connections to avoid modification during iteration
        connections_to_broadcast = self.active_connections.copy()

        for connection in connections_to_broadcast:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.debug("[web] Failed to send message to client: %s", e)
                # Client will be cleaned up by main handler on next receive


class EventBusListener:
    """Subscribes to EventBus topics and broadcasts to WebSocket clients."""

    def __init__(self, event_bus: EventBus, connection_manager: ConnectionManager):
        """Initialize listener.

        Args:
            event_bus: EventBus to subscribe to
            connection_manager: ConnectionManager for broadcasting
        """
        self.bus = event_bus
        self.manager = connection_manager
        self._subscribed = False
        self._app_state = {
            'last_pod_summaries': {},
            'recent_trades': [],
            'recent_governance': [],
            'recent_activity': [],
            'recent_orders': [],
        }

    async def subscribe(self):
        """Subscribe to all relevant EventBus topics."""
        if self._subscribed:
            return

        try:
            # Subscribe to pod gateway topics (pod summaries)
            await self.bus.subscribe("pod.equities.gateway", self._on_pod_update)
            await self.bus.subscribe("pod.fx.gateway", self._on_pod_update)
            await self.bus.subscribe("pod.crypto.gateway", self._on_pod_update)
            await self.bus.subscribe("pod.commodities.gateway", self._on_pod_update)

            # Subscribe to governance topics
            await self.bus.subscribe("governance.ceo", self._on_governance)
            await self.bus.subscribe("governance.cio", self._on_governance)
            await self.bus.subscribe("governance.cro", self._on_governance)

            # Subscribe to execution fill events
            await self.bus.subscribe("execution.fill", self._on_trade)

            # Subscribe to order lifecycle updates
            await self.bus.subscribe("execution.order_update", self._on_order_update)

            # Subscribe to risk alerts
            await self.bus.subscribe("risk.alert", self._on_risk_alert)

            # Subscribe to agent activity feed
            await self.bus.subscribe("agent.activity", self._on_agent_activity)

            self._subscribed = True
            logger.info("[web] EventBusListener subscribed to all topics")
        except Exception as e:
            logger.error("[web] Failed to subscribe to EventBus: %s", e)
            raise

    async def _on_pod_update(self, message: AgentMessage):
        """Handle pod summary update from EventBus."""
        try:
            payload = message.payload
            pod_id = payload.get("pod_id") or message.topic.split(".")[1]

            # Flatten risk_metrics to top level so dashboard can read directly
            rm = payload.get("risk_metrics", {})
            payload["nav"] = payload.get("nav") or rm.get("nav", 0)
            payload["daily_pnl"] = payload.get("daily_pnl") or rm.get("daily_pnl", 0)
            payload["starting_capital"] = rm.get("starting_capital", 0)
            payload["drawdown"] = rm.get("drawdown_from_hwm", 0)
            payload["vol_ann"] = rm.get("current_vol_ann", 0)
            payload["gross_leverage"] = rm.get("gross_leverage", 0)
            payload["net_leverage"] = rm.get("net_leverage", 0)
            payload["var_95"] = rm.get("var_95_1d", 0)
            payload["es_95"] = rm.get("es_95_1d", 0)
            # Map positions array for frontend compatibility
            payload["current_positions"] = payload.get("positions", payload.get("current_positions", []))
            payload["exposure_buckets"] = payload.get("exposure_buckets", [])

            broadcast_data = {
                "type": "pod_summary",
                "pod_id": pod_id,
                "timestamp": message.timestamp.isoformat(),
                "data": payload,
            }
            await self.manager.broadcast(broadcast_data)

            # Store for snapshot on reconnect
            if hasattr(self, '_app_state'):
                self._app_state['last_pod_summaries'][pod_id] = broadcast_data
        except Exception as e:
            logger.error("[web] Error broadcasting pod update: %s", e)

    async def _on_governance(self, message: AgentMessage):
        """Handle governance event from EventBus."""
        try:
            payload = message.payload
            mandate = payload.get("mandate", {})
            msg = {
                "type": "governance",
                "timestamp": message.timestamp.isoformat(),
                "data": {
                    "agent": payload.get("authorized_by", mandate.get("authorized_by", "CEO")).upper().replace("_LLM", "").replace("_RULE_BASED", ""),
                    "decision": payload.get("event_type", "MANDATE_UPDATE"),
                    "reasoning": mandate.get("rationale", mandate.get("narrative", "")),
                    "weights": mandate.get("pod_allocations", {}),
                    "narrative": mandate.get("narrative", ""),
                    "objectives": mandate.get("objectives", []),
                },
            }
            await self.manager.broadcast(msg)
            self._app_state['recent_governance'].insert(0, msg)
            if len(self._app_state['recent_governance']) > 20:
                self._app_state['recent_governance'] = self._app_state['recent_governance'][:20]
        except Exception as e:
            logger.error("[web] Error broadcasting governance event: %s", e)

    async def _on_trade(self, message: AgentMessage):
        """Handle execution fill event from EventBus."""
        try:
            msg = {
                "type": "trade",
                "timestamp": message.timestamp.isoformat(),
                "data": message.payload,
            }
            await self.manager.broadcast(msg)
            self._app_state['recent_trades'].insert(0, msg)
            if len(self._app_state['recent_trades']) > 50:
                self._app_state['recent_trades'] = self._app_state['recent_trades'][:50]
        except Exception as e:
            logger.error("[web] Error broadcasting trade event: %s", e)

    async def _on_risk_alert(self, message: AgentMessage):
        """Handle risk alert from EventBus."""
        try:
            await self.manager.broadcast(
                {
                    "type": "risk_alert",
                    "timestamp": message.timestamp.isoformat(),
                    "data": message.payload,
                }
            )
        except Exception as e:
            logger.error("[web] Error broadcasting risk alert: %s", e)

    async def _on_agent_activity(self, message: AgentMessage):
        """Handle agent activity from EventBus -- forward to WebSocket clients."""
        try:
            msg = {
                "type": "agent_activity",
                "timestamp": message.timestamp.isoformat(),
                "data": message.payload,
            }
            await self.manager.broadcast(msg)
            self._app_state['recent_activity'].insert(0, msg)
            if len(self._app_state['recent_activity']) > 50:
                self._app_state['recent_activity'] = self._app_state['recent_activity'][:50]
        except Exception as e:
            logger.error("[web] Error broadcasting agent activity: %s", e)

    async def _on_order_update(self, message: AgentMessage):
        """Handle order lifecycle event -- forward to WebSocket clients."""
        try:
            msg = {
                "type": "order_update",
                "timestamp": message.timestamp.isoformat(),
                "data": message.payload,
            }
            await self.manager.broadcast(msg)
            self._app_state['recent_orders'].insert(0, msg)
            if len(self._app_state['recent_orders']) > 50:
                self._app_state['recent_orders'] = self._app_state['recent_orders'][:50]
        except Exception as e:
            logger.error("[web] Error broadcasting order update: %s", e)

    def get_snapshot(self) -> dict:
        """Build a session snapshot for new WebSocket clients."""
        return {
            "type": "session_snapshot",
            "data": {
                "pod_summaries": self._app_state.get('last_pod_summaries', {}),
                "recent_trades": self._app_state.get('recent_trades', [])[:20],
                "recent_governance": self._app_state.get('recent_governance', [])[:10],
                "recent_activity": self._app_state.get('recent_activity', [])[:20],
                "recent_orders": self._app_state.get('recent_orders', [])[:30],
            },
        }


# Response models for REST endpoints
class PodSummaryResponse(BaseModel):
    """Pod summary for REST response."""

    pod_id: str
    nav: float
    daily_pnl: float
    status: str
    timestamp: str


class SessionInfoResponse(BaseModel):
    """Session info for REST response."""

    session_id: str
    capital_per_pod: float
    total_capital: float
    iteration: int
    uptime_seconds: float
    num_pods: int


class RiskStatusResponse(BaseModel):
    """Risk status for REST response."""

    risk_halt: bool
    risk_halt_reason: Optional[str]
    breached_pods: list[str]


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    timestamp: str


def create_app(
    event_bus: Optional[EventBus] = None,
    session_start_time: Optional[datetime] = None,
    session_manager=None,
) -> FastAPI:
    """Create FastAPI application.

    Args:
        event_bus: EventBus instance (for testing or explicit injection)
        session_start_time: Session start time (for testing)
        session_manager: SessionManager instance for session control

    Returns:
        FastAPI application instance
    """
    app = FastAPI(
        title="Agentic HF Mission Control",
        description="Real-time trading dashboard and governance API",
        version="2.1.0",
    )

    # Add CORS middleware for cross-origin requests
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # State
    manager = ConnectionManager()
    listener: Optional[EventBusListener] = None
    app.state.connection_manager = manager
    app.state.event_bus = event_bus
    app.state.session_start_time = session_start_time or datetime.now(timezone.utc)
    app.state.iteration = 0
    app.state.capital_per_pod = 0.0
    app.state.pod_summaries: dict[str, dict] = {}
    app.state.risk_halt = False
    app.state.risk_halt_reason: Optional[str] = None
    app.state.session_manager = session_manager
    if session_manager:
        session_manager._restartable = True

    @app.on_event("startup")
    async def startup():
        """Initialize EventBus listener on app startup."""
        nonlocal listener
        if app.state.event_bus:
            listener = EventBusListener(app.state.event_bus, manager)
            await listener.subscribe()
            logger.info("[web] App startup complete, EventBus listener subscribed")

    @app.on_event("shutdown")
    async def shutdown():
        """Cleanup on shutdown."""
        logger.info("[web] App shutting down, closing %d connections", len(manager.active_connections))
        for connection in manager.active_connections.copy():
            try:
                await connection.close()
            except Exception:
                pass

    # REST endpoints
    @app.get("/health", response_model=HealthResponse)
    async def health_check():
        """Health check endpoint."""
        return HealthResponse(status="ok", timestamp=datetime.now(timezone.utc).isoformat())

    @app.get("/api/session", response_model=SessionInfoResponse)
    async def get_session_info():
        """Get current session information."""
        uptime = (datetime.now(timezone.utc) - app.state.session_start_time).total_seconds()
        return SessionInfoResponse(
            session_id="live-session-1",
            capital_per_pod=app.state.capital_per_pod,
            total_capital=app.state.capital_per_pod * 4,  # 4 pods
            iteration=app.state.iteration,
            uptime_seconds=uptime,
            num_pods=4,
        )

    @app.get("/api/pods", response_model=dict)
    async def get_all_pods():
        """Get all pod summaries."""
        pods = []
        for pod_id, summary in app.state.pod_summaries.items():
            # Try to get nav from risk_metrics first, then fall back to top level
            nav = summary.get("nav")
            if nav is None:
                nav = summary.get("risk_metrics", {}).get("nav", 0.0)

            # Try to get daily_pnl from risk_metrics first, then fall back to top level
            daily_pnl = summary.get("daily_pnl")
            if daily_pnl is None:
                daily_pnl = summary.get("risk_metrics", {}).get("daily_pnl", 0.0)

            status = summary.get("status", "UNKNOWN")

            pods.append(
                PodSummaryResponse(
                    pod_id=pod_id,
                    nav=nav,
                    daily_pnl=daily_pnl,
                    status=status,
                    timestamp=summary.get("timestamp", datetime.now(timezone.utc).isoformat()),
                ).model_dump()
            )

        return {"pods": pods, "count": len(pods)}

    @app.get("/api/pods/{pod_id}", response_model=dict)
    async def get_pod_detail(pod_id: str):
        """Get detailed pod summary."""
        summary = app.state.pod_summaries.get(pod_id)
        if not summary:
            raise HTTPException(status_code=404, detail=f"Pod {pod_id} not found")

        return {"pod_id": pod_id, "data": summary}

    @app.get("/api/risk", response_model=RiskStatusResponse)
    async def get_risk_status():
        """Get current risk status."""
        return RiskStatusResponse(
            risk_halt=app.state.risk_halt,
            risk_halt_reason=app.state.risk_halt_reason,
            breached_pods=[],
        )

    @app.get("/api/audit", response_model=dict)
    async def get_audit_log():
        """Get recent audit log entries (stub for MVP)."""
        return {
            "entries": [],
            "count": 0,
            "note": "Audit log endpoint not yet implemented",
        }

    # --- Session control endpoints ---

    @app.get("/api/session/status")
    async def get_session_status():
        """Get current session status (active, iteration, uptime)."""
        sm = app.state.session_manager
        active = sm.session_active if sm else False
        iteration = sm.iteration if sm else app.state.iteration
        uptime = (datetime.now(timezone.utc) - app.state.session_start_time).total_seconds() if active else 0
        pod_count = len(sm._pod_runtimes) if sm and hasattr(sm, '_pod_runtimes') else 0
        return {
            "active": active,
            "iteration": iteration,
            "uptime_seconds": round(uptime, 1),
            "pod_count": pod_count,
        }

    @app.post("/api/session/stop")
    async def stop_session():
        """Stop the running trading session."""
        sm = app.state.session_manager
        if not sm:
            raise HTTPException(status_code=503, detail="SessionManager not available")
        if not sm.session_active:
            return {"ok": False, "detail": "Session is not running"}
        try:
            await sm.stop_session()
            status_msg = {
                "type": "session_status",
                "data": {"active": False, "iteration": sm.iteration},
            }
            await manager.broadcast(status_msg)
            return {"ok": True, "detail": "Session stopped"}
        except Exception as exc:
            logger.error("[web] stop_session failed: %s", exc)
            raise HTTPException(status_code=500, detail=str(exc))

    @app.post("/api/session/start")
    async def start_session():
        """Start a new trading session (if not already running)."""
        sm = app.state.session_manager
        if not sm:
            raise HTTPException(status_code=503, detail="SessionManager not available")
        if sm.session_active:
            return {"ok": False, "detail": "Session is already running"}
        try:
            async def _run():
                await sm.start_live_session()
                await sm.run_event_loop(interval_seconds=60.0, governance_freq=5)
            asyncio.ensure_future(_run())
            await asyncio.sleep(0.5)
            status_msg = {
                "type": "session_status",
                "data": {"active": True, "iteration": sm.iteration},
            }
            await manager.broadcast(status_msg)
            app.state.session_start_time = datetime.now(timezone.utc)
            return {"ok": True, "detail": "Session starting"}
        except Exception as exc:
            logger.error("[web] start_session failed: %s", exc)
            raise HTTPException(status_code=500, detail=str(exc))

    # WebSocket endpoint
    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        """WebSocket endpoint for real-time updates."""
        await manager.connect(websocket)
        try:
            # Send session snapshot on connect so client recovers state
            if listener:
                snapshot = listener.get_snapshot()
                snapshot["data"]["iteration"] = app.state.iteration
                sm = app.state.session_manager
                snapshot["data"]["session_active"] = sm.session_active if sm else False
                await websocket.send_json(snapshot)
            while True:
                data = await websocket.receive_text()
                logger.debug("[web] Received from WebSocket: %s", data)
        except WebSocketDisconnect:
            await manager.disconnect(websocket)
        except Exception as e:
            logger.error("[web] WebSocket error: %s", e)
            await manager.disconnect(websocket)

    # Helper to update app state (called by SessionManager)
    async def update_session_state(
        iteration: int,
        capital_per_pod: float,
        pod_summaries: dict[str, dict],
        risk_halt: bool = False,
        risk_halt_reason: Optional[str] = None,
    ):
        """Update session state in app (called by SessionManager)."""
        app.state.iteration = iteration
        app.state.capital_per_pod = capital_per_pod
        app.state.pod_summaries = pod_summaries
        app.state.risk_halt = risk_halt
        app.state.risk_halt_reason = risk_halt_reason

    app.state.update_session_state = update_session_state

    # --- Static file serving for the web dashboard ---
    # Resolve the path to web/dist/ relative to this file (src/web/server.py -> ../../web/dist)
    _static_dir = Path(os.path.join(os.path.dirname(__file__), "../../web/dist")).resolve()
    _index_html = _static_dir / "index.html"

    if _static_dir.is_dir():
        @app.get("/")
        async def serve_root():
            """Serve the dashboard index.html at the root path."""
            if _index_html.is_file():
                return FileResponse(
                    str(_index_html),
                    media_type="text/html",
                    headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
                )
            raise HTTPException(status_code=404, detail="index.html not found in web/dist/")

        # Mount static files LAST so API routes (/api/*, /ws, /health) take priority
        app.mount("/", StaticFiles(directory=str(_static_dir), html=False), name="static")
        logger.info("[web] Serving static files from %s", _static_dir)
    else:
        logger.warning("[web] Static directory not found: %s — dashboard will not be served", _static_dir)

    return app


# Create app instance for uvicorn
app = create_app()
