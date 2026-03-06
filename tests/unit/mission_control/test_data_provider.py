"""Tests for DataProvider service."""
import pytest
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
