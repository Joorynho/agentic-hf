"""DataProvider service — maintains live state from EventBus for TUI."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from src.core.bus.event_bus import EventBus
from src.core.bus.audit_log import AuditLog
from src.core.models.pod_summary import PodSummary

logger = logging.getLogger(__name__)


class DataProvider:
    """Exposes live firm state via EventBus subscriptions.

    Maintains:
    - Pod summaries (latest for each pod)
    - Firm-level metrics (aggregate NAV, PnL, risk)
    - Recent governance conversations
    - Audit log entries

    Screens inject this service and access data via properties.
    """

    def __init__(self, bus: EventBus, audit_log: Optional[AuditLog] = None):
        """Initialize DataProvider with EventBus connection.

        Args:
            bus: EventBus instance for subscribing to pod summaries
            audit_log: AuditLog for querying conversations/events
        """
        self._bus = bus
        self._audit_log = audit_log
        self._pod_summaries: dict[str, PodSummary] = {}
        self._recent_conversations: list = []

        logger.info("[data_provider] Initialized")

    @property
    def firm_nav(self) -> float:
        """Aggregate NAV across all pods (or 0 if none)."""
        if not self._pod_summaries:
            return 0.0
        total = 0.0
        for s in self._pod_summaries.values():
            if isinstance(s, dict):
                # Handle raw dict payloads from _on_pod_summary
                nav = s.get('risk_metrics', {}).get('nav', 0.0) if isinstance(s.get('risk_metrics'), dict) else s.get('nav', 0.0)
                total += nav
            else:
                # Handle PodSummary objects
                total += s.risk_metrics.nav
        return total

    @property
    def firm_daily_pnl(self) -> float:
        """Aggregate daily PnL across all pods."""
        if not self._pod_summaries:
            return 0.0
        total = 0.0
        for s in self._pod_summaries.values():
            if isinstance(s, dict):
                # Handle raw dict payloads from _on_pod_summary
                pnl = s.get('risk_metrics', {}).get('daily_pnl', 0.0) if isinstance(s.get('risk_metrics'), dict) else s.get('daily_pnl', 0.0)
                total += pnl
            else:
                # Handle PodSummary objects
                total += s.risk_metrics.daily_pnl
        return total

    @property
    def pod_summaries(self) -> dict[str, PodSummary]:
        """Latest pod summary for each pod_id."""
        return self._pod_summaries.copy()

    @property
    def recent_conversations(self) -> list:
        """Recent governance loop transcripts."""
        return self._recent_conversations.copy()

    @property
    def audit_entries(self) -> list:
        """Recent audit log entries (risk alerts, governance decisions, etc)."""
        if self._audit_log:
            # Query last 50 entries sorted by timestamp desc
            return self._audit_log.query(
                "SELECT * FROM messages ORDER BY timestamp DESC LIMIT 50"
            )
        return []

    async def subscribe_to_updates(self) -> None:
        """Subscribe to EventBus topics for live updates.

        Called once at app startup to wire up subscriptions.
        Subscribes to concrete pod gateway topics for the 5 design pods.
        """
        # Subscribe to pod gateway summaries for each of the 5 design pods
        POD_IDS = ["alpha", "beta", "gamma", "delta", "epsilon"]
        for pod_id in POD_IDS:
            topic = f"pod.{pod_id}.gateway"
            await self._bus.subscribe(topic, self._on_pod_summary)
            logger.debug("[data_provider] Subscribed to %s", topic)

        # Subscribe to governance loops
        await self._bus.subscribe("governance.*", self._on_governance_event)

        logger.info("[data_provider] Subscribed to EventBus topics (%d pod topics)", len(POD_IDS))

    async def _on_pod_summary(self, msg) -> None:
        """Handle pod summary update from gateway."""
        if hasattr(msg, 'payload') and isinstance(msg.payload, dict):
            pod_id = msg.payload.get('pod_id')
            # For now, store the message payload; actual PodSummary
            # construction happens in session manager
            if pod_id:
                self._pod_summaries[pod_id] = msg.payload
                logger.debug("[data_provider] Updated pod %s", pod_id)

    async def _on_governance_event(self, msg) -> None:
        """Handle governance loop completion."""
        # Store recent conversation if available
        if hasattr(msg, 'payload'):
            self._recent_conversations.insert(0, msg.payload)
            # Keep only last 10 conversations
            self._recent_conversations = self._recent_conversations[:10]

    def reset(self) -> None:
        """Clear all cached data (useful for testing)."""
        self._pod_summaries.clear()
        self._recent_conversations.clear()
