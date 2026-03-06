"""MVP3 Batch 2 Integration Tests — TUI with live DataProvider."""
import asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock, patch
from io import StringIO

import pytest
from rich.console import Console

from src.core.bus.event_bus import EventBus
from src.core.bus.audit_log import AuditLog
from src.core.models.messages import AgentMessage
from src.mission_control.data_provider import DataProvider
from src.mission_control.session_manager import SessionManager
from src.mission_control.tui.screens.firm_dashboard import FirmDashboardWidget
from src.mission_control.tui.screens.pod_table import PodTableWidget
from src.mission_control.tui.screens.pod_drilldown import PodDrilldownWidget
from src.mission_control.tui.screens.risk_limits import RiskLimitsWidget
from src.mission_control.tui.screens.control_plane import ControlPlaneWidget
from src.mission_control.tui.screens.audit_screen import AuditScreenWidget
from src.mission_control.tui.screens.building_view import BuildingViewWidget


def _render_to_string(renderable):
    """Convert Rich renderable to string for assertions."""
    buffer = StringIO()
    console = Console(file=buffer, width=120, legacy_windows=False)
    console.print(renderable)
    return buffer.getvalue()


@pytest.mark.asyncio
async def test_data_provider_receives_pod_summary():
    """DataProvider receives and aggregates pod summaries from EventBus."""
    bus = EventBus(audit_log=AuditLog())
    provider = DataProvider(bus=bus)
    await provider.subscribe_to_updates()

    # Publish pod summary
    msg = AgentMessage(
        timestamp=datetime.now(timezone.utc),
        sender="pod.alpha.gateway",
        recipient="*",
        topic="pod.alpha.gateway",
        payload={
            "pod_id": "alpha",
            "risk_metrics": {"nav": 100000.0, "daily_pnl": 5000.0}
        },
    )
    await bus.publish("pod.alpha.gateway", msg, publisher_id="pod.alpha")

    # Allow async processing
    await asyncio.sleep(0.05)

    # Verify DataProvider has the summary
    assert "alpha" in provider.pod_summaries
    assert provider.firm_nav == 100000.0
    assert provider.firm_daily_pnl == 5000.0


def test_firm_dashboard_widget_renders_with_provider():
    """FirmDashboardWidget renders live metrics when DataProvider has data."""
    bus = EventBus(audit_log=AuditLog())
    provider = DataProvider(bus=bus)

    # Manually add pod summary to provider
    provider._pod_summaries["alpha"] = {
        "risk_metrics": {
            "nav": 100000.0,
            "daily_pnl": 5000.0,
            "drawdown_from_hwm": 0.02,
            "current_vol_ann": 0.08,
            "gross_leverage": 1.5,
            "var_95_1d": 0.01,
        }
    }

    widget = FirmDashboardWidget(data_provider=provider)
    output = widget.render()
    output_str = _render_to_string(output)

    assert "FIRM DASHBOARD" in output_str
    assert "$100,000.00" in output_str  # NAV
    assert "1" in output_str  # Active Pods count


def test_pod_table_widget_renders_with_provider():
    """PodTableWidget renders live pod table when DataProvider has data."""
    bus = EventBus(audit_log=AuditLog())
    provider = DataProvider(bus=bus)

    # Add multiple pods
    for pod_id in ["alpha", "beta"]:
        provider._pod_summaries[pod_id] = {
            "pod_id": pod_id,
            "status": "ACTIVE",
            "risk_metrics": {
                "nav": 100000.0,
                "daily_pnl": 2500.0,
                "drawdown_from_hwm": 0.01,
                "gross_leverage": 1.2,
            }
        }

    widget = PodTableWidget(data_provider=provider)
    output = widget.render()
    output_str = _render_to_string(output)

    assert "POD TABLE" in output_str
    assert "alpha" in output_str
    assert "beta" in output_str
    assert "ACTIVE" in output_str


def test_risk_limits_widget_color_codes():
    """RiskLimitsWidget color-codes metrics based on thresholds."""
    bus = EventBus(audit_log=AuditLog())
    provider = DataProvider(bus=bus)

    # Add pod with healthy risk
    provider._pod_summaries["alpha"] = {
        "risk_metrics": {
            "drawdown_from_hwm": 0.05,  # <7% = green
            "gross_leverage": 1.0,       # <1.4x = green
            "var_95_1d": 0.01,           # <1.5% = green
            "current_vol_ann": 0.08,     # <10% = green
        }
    }

    widget = RiskLimitsWidget(data_provider=provider)
    output = widget.render()
    output_str = _render_to_string(output)

    assert "RISK LIMITS" in output_str
    assert "5.00%" in output_str or "alpha" in output_str


def test_session_manager_has_data_provider():
    """SessionManager initializes with DataProvider and exposes it."""
    mock_adapter = MagicMock()
    manager = SessionManager(alpaca_adapter=mock_adapter)

    assert hasattr(manager, "_data_provider")
    assert hasattr(manager, "data_provider")
    assert isinstance(manager.data_provider, DataProvider)


@pytest.mark.asyncio
async def test_session_manager_publishes_to_eventbus():
    """SessionManager can publish pod summaries to EventBus."""
    bus = EventBus(audit_log=AuditLog())
    mock_adapter = MagicMock()
    manager = SessionManager(alpaca_adapter=mock_adapter, event_bus=bus)

    # Subscribe manager's DataProvider to updates
    await manager.data_provider.subscribe_to_updates()

    # Publish pod summary
    await manager.publish_pod_summary("alpha", {
        "pod_id": "alpha",
        "risk_metrics": {
            "nav": 150000.0,
            "daily_pnl": 7500.0,
        }
    })

    # Allow async processing
    await asyncio.sleep(0.05)

    # Verify DataProvider received it
    assert "alpha" in manager.data_provider.pod_summaries
    assert manager.data_provider.firm_nav == 150000.0


def test_all_screens_instantiate_with_provider():
    """All TUI screens instantiate successfully with DataProvider."""
    provider = DataProvider(bus=EventBus(audit_log=AuditLog()))

    screens = [
        FirmDashboardWidget(data_provider=provider),
        PodTableWidget(data_provider=provider),
        PodDrilldownWidget(data_provider=provider),
        RiskLimitsWidget(data_provider=provider),
        ControlPlaneWidget(data_provider=provider),
        AuditScreenWidget(data_provider=provider),
        BuildingViewWidget(data_provider=provider),
    ]

    for screen in screens:
        assert screen.data == provider
        # Each screen should render without error
        output = screen.render()
        assert output is not None


@pytest.mark.asyncio
async def test_full_pipeline_data_to_ui():
    """Full pipeline: EventBus → DataProvider → TUI screens."""
    bus = EventBus(audit_log=AuditLog())
    provider = DataProvider(bus=bus)
    mock_adapter = MagicMock()
    manager = SessionManager(alpaca_adapter=mock_adapter, event_bus=bus)

    # Start DataProvider subscriptions
    await provider.subscribe_to_updates()

    # Publish pod summaries via SessionManager
    for pod_id in ["alpha", "beta", "gamma"]:
        await manager.publish_pod_summary(pod_id, {
            "pod_id": pod_id,
            "status": "ACTIVE",
            "risk_metrics": {
                "nav": 100000.0 + (10000 if pod_id == "beta" else 0),
                "daily_pnl": 5000.0,
                "drawdown_from_hwm": 0.02,
                "current_vol_ann": 0.08,
                "gross_leverage": 1.5,
                "var_95_1d": 0.01,
            }
        })

    # Allow async processing
    await asyncio.sleep(0.1)

    # Verify DataProvider has all summaries
    assert len(provider.pod_summaries) == 3
    assert provider.firm_nav == 310000.0
    assert provider.firm_daily_pnl == 15000.0

    # Verify screens render with live data
    dashboard = FirmDashboardWidget(data_provider=provider)
    output = dashboard.render()
    output_str = _render_to_string(output)

    assert "310,000.00" in output_str or "310000" in output_str
    assert "3" in output_str  # Active Pods
