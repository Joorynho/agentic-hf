"""F8 — Audit Log screen (MVP3 real data)."""
from textual.widgets import Static
from textual.reactive import Reactive
from rich.panel import Panel
from rich.table import Table

from src.mission_control.data_provider import DataProvider


class AuditScreenWidget(Static):
    """Real-time audit log: risk alerts, governance events, trades."""

    data: Reactive[DataProvider | None] = Reactive(None)

    def __init__(self, data_provider: DataProvider | None = None, **kwargs):
        super().__init__(**kwargs)
        self.data = data_provider

    def render(self) -> Panel:
        if not self.data:
            return Panel(
                "[yellow]No audit data available[/yellow]",
                title="[bold cyan]AUDIT LOG[/bold cyan]",
                border_style="bright_blue",
            )

        entries = self.data.audit_entries
        if not entries:
            return Panel(
                "[dim]No events yet[/dim]",
                title="[bold cyan]AUDIT LOG[/bold cyan]",
                border_style="bright_blue",
            )

        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Time", width=12)
        table.add_column("Type", width=15)
        table.add_column("Message", width=40)

        for entry in entries[:20]:  # Show last 20
            if isinstance(entry, dict):
                timestamp = entry.get('timestamp', '')[:8]  # HH:MM:SS
                event_type = entry.get('event_type', 'unknown')
                message = str(entry.get('message', ''))[:40]
            else:
                timestamp = str(entry.timestamp)[:8]
                event_type = 'unknown'
                message = str(entry)[:40]

            table.add_row(timestamp, event_type, message)

        return Panel(
            table,
            title="[bold cyan]AUDIT LOG[/bold cyan]",
            subtitle="[dim]F8 — Last 20 events[/dim]",
            border_style="bright_blue",
        )

    def watch_data(self, data: DataProvider | None) -> None:
        """Re-render when data changes."""
        self.refresh()


# Legacy alias for backward compatibility with app.py imports
AuditWidget = AuditScreenWidget
