"""Tests for DataProvider service."""
import pytest
import asyncio
from unittest.mock import MagicMock
from src.core.bus.event_bus import EventBus
from src.core.bus.audit_log import AuditLog
from src.mission_control.data_provider import DataProvider


def test_data_provider_init():
    """DataProvider initializes with EventBus and AuditLog."""
    bus = EventBus(audit_log=AuditLog())
    provider = DataProvider(bus=bus)
    assert provider._bus is bus
    assert provider.firm_nav == 0.0
    assert provider.pod_summaries == {}


def test_data_provider_has_recent_conversations():
    """DataProvider exposes recent governance conversations."""
    bus = EventBus(audit_log=AuditLog())
    provider = DataProvider(bus=bus)
    assert isinstance(provider.recent_conversations, list)


@pytest.mark.asyncio
async def test_data_provider_on_pod_summary_stores_payload():
    """_on_pod_summary stores pod payload in _pod_summaries."""
    bus = EventBus(audit_log=AuditLog())
    provider = DataProvider(bus=bus)

    # Create a mock message with pod summary payload
    msg = MagicMock()
    msg.payload = {
        'pod_id': 'alpha',
        'risk_metrics': {
            'nav': 100000.0,
            'daily_pnl': 5000.0,
        }
    }

    # Call the handler directly
    await provider._on_pod_summary(msg)

    # Verify it was stored
    assert 'alpha' in provider.pod_summaries
    assert provider.pod_summaries['alpha']['pod_id'] == 'alpha'
    assert provider.firm_nav == 100000.0
    assert provider.firm_daily_pnl == 5000.0
