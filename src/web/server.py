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
            'position_reviews': [],
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

            is_full_summary = "risk_metrics" in payload or "positions" in payload

            if is_full_summary:
                rm = payload.get("risk_metrics", {})
                payload["nav"] = payload.get("nav") or rm.get("nav", 0)
                payload["daily_pnl"] = payload.get("daily_pnl") or rm.get("daily_pnl", 0)
                payload["realized_pnl"] = rm.get("realized_pnl", 0)
                payload["starting_capital"] = rm.get("starting_capital", 0)
                payload["invested"] = rm.get("invested", 0)
                payload["cash"] = rm.get("cash", 0)
                payload["drawdown"] = rm.get("drawdown_from_hwm", 0)
                payload["vol_ann"] = rm.get("current_vol_ann", 0)
                payload["gross_leverage"] = rm.get("gross_leverage", 0)
                payload["net_leverage"] = rm.get("net_leverage", 0)
                payload["var_95"] = rm.get("var_95_1d", 0)
                payload["es_95"] = rm.get("es_95_1d", 0)
                payload["current_positions"] = payload.get("positions", payload.get("current_positions", []))
                payload["exposure_buckets"] = payload.get("exposure_buckets", [])
                payload["macro_regime"] = payload.get("macro_regime")
                payload["performance_metrics"] = payload.get("performance_metrics", {})
                payload["trade_outcome_stats"] = payload.get("trade_outcome_stats", {})

            broadcast_data = {
                "type": "pod_summary" if is_full_summary else "pod_enrichment",
                "pod_id": pod_id,
                "timestamp": message.timestamp.isoformat(),
                "data": payload,
            }
            await self.manager.broadcast(broadcast_data)

            if hasattr(self, '_app_state'):
                if is_full_summary:
                    # Preserve research keys from existing summary; full summaries (e.g. price ticker)
                    # don't include fred_snapshot, polymarket_signals, etc., so merge them in
                    existing = self._app_state['last_pod_summaries'].get(pod_id, {})
                    existing_data = existing.get("data", {})
                    research_keys = (
                        "polymarket_signals", "polymarket_confidence", "macro_score",
                        "fred_snapshot", "fred_score", "poly_sentiment", "social_score",
                        "x_feed", "x_tweet_count", "news_last_refresh", "features",
                    )
                    for key in research_keys:
                        if key not in payload and key in existing_data:
                            payload[key] = existing_data[key]
                    broadcast_data["data"] = payload
                    self._app_state['last_pod_summaries'][pod_id] = broadcast_data
                else:
                    existing = self._app_state['last_pod_summaries'].get(pod_id, {})
                    if existing:
                        existing_data = existing.get("data", {})
                        # Never overwrite positions with empty during enrichment merge
                        merge_payload = dict(payload)
                        for k in ("positions", "current_positions"):
                            if k in merge_payload and (not merge_payload[k] or (isinstance(merge_payload[k], list) and len(merge_payload[k]) == 0)):
                                del merge_payload[k]
                        existing_data.update(merge_payload)
                        existing["data"] = existing_data
                        existing["timestamp"] = message.timestamp.isoformat()
                    else:
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

            action = (message.payload or {}).get("action", "")
            if action.startswith("position_review") or action in ("review_started", "review_completed"):
                review_msg = {
                    "type": "position_review",
                    "timestamp": message.timestamp.isoformat(),
                    "data": message.payload,
                }
                await self.manager.broadcast(review_msg)
                self._app_state['position_reviews'].append(review_msg)
                if len(self._app_state['position_reviews']) > 100:
                    self._app_state['position_reviews'] = self._app_state['position_reviews'][-100:]
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

    def inject_restored_memory(self, memory: dict) -> None:
        """Pre-populate app state from restored session memory (called on startup)."""
        trades = memory.get("trades", [])
        for t in trades:
            self._app_state['recent_trades'].append({
                "type": "trade",
                "timestamp": t.get("timestamp", ""),
                "data": {
                    "pod_id": t.get("pod_id", "unknown"),
                    "symbol": t.get("symbol", ""),
                    "side": t.get("side", ""),
                    "qty": t.get("qty", 0),
                    "fill_price": t.get("filled_price") or t.get("fill_price", 0),
                    "order_id": t.get("order_id"),
                    "status": "FILLED",
                },
            })
        self._app_state['recent_trades'] = self._app_state['recent_trades'][-50:]

        governance = memory.get("governance", [])
        for g in governance:
            # Transform raw governance dict to the same format _on_governance produces
            auth_by = g.get("authorized_by", "CEO")
            agent_label = auth_by.upper().replace("_LLM", "").replace("_RULE_BASED", "") if auth_by else "CEO"
            self._app_state['recent_governance'].append({
                "type": "governance",
                "timestamp": g.get("ts", g.get("timestamp", "")),
                "data": {
                    "agent": agent_label,
                    "decision": "MANDATE_UPDATE",
                    "reasoning": g.get("rationale", g.get("narrative", "")),
                    "weights": g.get("pod_allocations", {}),
                    "narrative": g.get("narrative", ""),
                    "objectives": g.get("objectives", []),
                },
            })
        self._app_state['recent_governance'] = self._app_state['recent_governance'][-20:]
        logger.info("[web] Injected restored memory: %d trades, %d governance", len(trades), len(governance))

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
                "position_reviews": self._app_state.get('position_reviews', []),
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
            app.state.listener = listener
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

    @app.get("/api/position/{pod_id}/{symbol}")
    async def get_position_detail(pod_id: str, symbol: str):
        """Get full position detail including fill history."""
        sm = app.state.session_manager
        if not sm:
            raise HTTPException(status_code=503, detail="Session not initialized")
        detail = sm.get_position_detail(pod_id, symbol.upper())
        if not detail:
            raise HTTPException(status_code=404, detail=f"Position {symbol} not found in {pod_id}")
        return detail

    @app.get("/api/trades/closed")
    async def get_closed_trades():
        """Get all closed trades across all pods."""
        sm = app.state.session_manager
        if not sm:
            raise HTTPException(status_code=503, detail="Session not initialized")
        return sm.get_all_closed_trades()

    @app.get("/api/positions")
    async def get_current_positions():
        """Get all current (open) positions across pods. Primary source for Top Holdings table.
        Reads directly from SessionManager accountants — bypasses EventBus/WebSocket."""
        sm = app.state.session_manager
        if sm and hasattr(sm, "get_all_positions"):
            positions = sm.get_all_positions()
            return {"positions": positions}
        # Fallback when session not started
        result = []
        for pod_id, summary in (app.state.pod_summaries or {}).items():
            positions = summary.get("current_positions") or summary.get("positions") or []
            for p in positions if isinstance(positions, list) else []:
                if p and (p.get("symbol") or p.get("qty") is not None):
                    row = dict(p)
                    row["_pod"] = pod_id
                    result.append(row)
        return {"positions": result}

    @app.get("/api/closed-positions")
    async def get_closed_positions():
        """Get all closed positions across all pods, sorted by exit time descending."""
        sm = app.state.session_manager
        if not sm:
            raise HTTPException(status_code=503, detail="Session not initialized")
        trades = sm.get_all_closed_trades()
        return {"closed_positions": trades}

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
                await sm.run_event_loop(interval_seconds=60.0, governance_freq=2)
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

    # --- Reports endpoints ---
    _reports_dir = Path(os.path.join(os.path.dirname(__file__), "../../reports")).resolve()
    _reports_dir.mkdir(parents=True, exist_ok=True)

    @app.get("/api/reports")
    async def list_reports():
        """List available daily reports (max 5, most recent first)."""
        files = sorted(_reports_dir.glob("review_*.html"), key=lambda f: f.stat().st_mtime, reverse=True)[:5]
        result = []
        for f in files:
            stat = f.stat()
            result.append({
                "filename": f.name,
                "date": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                "size_kb": round(stat.st_size / 1024, 1),
            })
        return {"reports": result}

    @app.get("/api/reports/{filename}")
    async def download_report(filename: str):
        """Download a specific report file."""
        if ".." in filename or "/" in filename or "\\" in filename:
            raise HTTPException(status_code=400, detail="Invalid filename")
        fpath = _reports_dir / filename
        if not fpath.is_file():
            raise HTTPException(status_code=404, detail="Report not found")
        return FileResponse(
            str(fpath),
            media_type="text/html",
            filename=filename,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

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
                # Merge app.state.pod_summaries into snapshot so positions are never stale
                # (last_pod_summaries may be empty or lack positions if populated only from EventBus)
                for pod_id, raw in (app.state.pod_summaries or {}).items():
                    rm = raw.get("risk_metrics") or {}
                    data = dict(raw)
                    data["nav"] = data.get("nav") or rm.get("nav", 0)
                    data["daily_pnl"] = data.get("daily_pnl") or rm.get("daily_pnl", 0)
                    data["current_positions"] = data.get("current_positions") or data.get("positions", [])
                    data["positions"] = data["current_positions"]
                    existing = snapshot["data"]["pod_summaries"].get(pod_id, {})
                    existing_data = existing.get("data", {}) if isinstance(existing, dict) else {}
                    existing_data.update(data)
                    snapshot["data"]["pod_summaries"][pod_id] = {
                        "type": "pod_summary",
                        "pod_id": pod_id,
                        "data": existing_data,
                        "timestamp": raw.get("timestamp", existing.get("timestamp", "")),
                    }
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

        # Broadcast iteration update so dashboard shows real iteration count
        if hasattr(app.state, "listener") and app.state.listener is not None:
            try:
                await app.state.listener.manager.broadcast({
                    "type": "session_status",
                    "data": {"active": True, "iteration": iteration},
                })
            except Exception:
                pass

        # Sync into listener's last_pod_summaries so WebSocket snapshot includes research data
        # (Research tab reads fred_snapshot, polymarket_signals, x_feed from pod_summaries)
        if hasattr(app.state, "listener") and app.state.listener is not None:
            listener = app.state.listener
            if hasattr(listener, "_app_state"):
                ts = datetime.now(timezone.utc).isoformat()
                for pod_id, raw in pod_summaries.items():
                    rm = raw.get("risk_metrics") or {}
                    data = dict(raw)
                    data["nav"] = data.get("nav") or rm.get("nav", 0)
                    data["daily_pnl"] = data.get("daily_pnl") or rm.get("daily_pnl", 0)
                    data["realized_pnl"] = rm.get("realized_pnl", 0)
                    data["starting_capital"] = rm.get("starting_capital", 0)
                    data["invested"] = rm.get("invested", 0)
                    data["cash"] = rm.get("cash", 0)
                    data["current_positions"] = data.get("current_positions") or data.get("positions", [])
                    listener._app_state["last_pod_summaries"][pod_id] = {
                        "type": "pod_summary",
                        "pod_id": pod_id,
                        "data": data,
                        "timestamp": ts,
                    }

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
