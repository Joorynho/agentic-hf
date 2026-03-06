"""F6 — Control Plane screen (MVP3 real data)."""
from textual.widgets import Static
from textual.reactive import Reactive
from rich.panel import Panel
from rich.table import Table

from src.mission_control.data_provider import DataProvider


class ControlPlaneWidget(Static):
    """Capital allocation and pod control."""

    data: Reactive[DataProvider | None] = Reactive(None)

    def __init__(self, data_provider: DataProvider | None = None, **kwargs):
        super().__init__(**kwargs)
        self.data = data_provider

    def render(self) -> Panel:
        if not self.data or not self.data.pod_summaries:
            return Panel(
                "[yellow]No allocation data available[/yellow]",
                title="[bold cyan]CONTROL PLANE[/bold cyan]",
                border_style="bright_blue",
            )

        table = Table.grid(padding=(0, 2))
        table.add_column("Pod", style="cyan", width=12)
        table.add_column("Allocation", width=15)
        table.add_column("Status", width=12)
        table.add_column("Action", width=20)

        pods = self.data.pod_summaries
        equal_alloc = 1.0 / len(pods) if pods else 0

        for pod_id in sorted(pods.keys()):
            summary = pods[pod_id]
            status = summary.get('status', 'UNKNOWN') if isinstance(summary, dict) else summary.status.value
            status_color = {"ACTIVE": "green", "PAUSED": "yellow", "HALTED": "red"}.get(str(status), "white")

            table.add_row(
                pod_id,
                f"{equal_alloc:.1%}",
                f"[{status_color}]{status}[/{status_color}]",
                "[dim](reserve for future)[/dim]",
            )

        return Panel(
            table,
            title="[bold cyan]CONTROL PLANE[/bold cyan]",
            subtitle="[dim]F6[/dim]",
            border_style="bright_blue",
        )

    def watch_data(self, data: DataProvider | None) -> None:
        """Re-render when data changes."""
        self.refresh()
