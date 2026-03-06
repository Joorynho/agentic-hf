"""F2 — Pod Table screen (MVP3 real data)."""
from textual.widgets import Static
from textual.reactive import Reactive
from rich.panel import Panel
from rich.table import Table

from src.mission_control.data_provider import DataProvider


class PodTableWidget(Static):
    """Live pod table with real NAV, PnL, risk metrics."""

    data: Reactive[DataProvider | None] = Reactive(None)

    def __init__(self, data_provider: DataProvider | None = None, **kwargs):
        super().__init__(**kwargs)
        self.data = data_provider

    def render(self) -> Panel:
        if not self.data or not self.data.pod_summaries:
            return Panel(
                "[yellow]No pod data available[/yellow]",
                title="[bold cyan]POD TABLE[/bold cyan]",
                border_style="bright_blue",
            )

        table = Table(title="Active Pods", show_header=True, header_style="bold magenta")
        table.add_column("Pod ID", style="cyan", width=12)
        table.add_column("NAV", style="green", width=15)
        table.add_column("Daily PnL", width=12)
        table.add_column("Status", width=10)
        table.add_column("Drawdown", width=10)
        table.add_column("Leverage", width=10)

        for pod_id, summary in self.data.pod_summaries.items():
            # Handle both dict and PodSummary objects
            if isinstance(summary, dict):
                nav = summary.get('risk_metrics', {}).get('nav', 0.0)
                pnl = summary.get('risk_metrics', {}).get('daily_pnl', 0.0)
                drawdown = summary.get('risk_metrics', {}).get('drawdown_from_hwm', 0.0)
                leverage = summary.get('risk_metrics', {}).get('gross_leverage', 0.0)
                status = summary.get('status', 'UNKNOWN')
            else:
                nav = summary.risk_metrics.nav
                pnl = summary.risk_metrics.daily_pnl
                drawdown = summary.risk_metrics.drawdown_from_hwm
                leverage = summary.risk_metrics.gross_leverage
                status = summary.status.value

            pnl_color = "green" if pnl >= 0 else "red"
            status_color = {"ACTIVE": "green", "PAUSED": "yellow", "HALTED": "red"}.get(str(status), "white")

            table.add_row(
                pod_id,
                f"${nav:,.0f}",
                f"[{pnl_color}]${pnl:,.0f}[/{pnl_color}]",
                f"[{status_color}]{status}[/{status_color}]",
                f"{drawdown:.2%}",
                f"{leverage:.2f}x",
            )

        return Panel(
            table,
            title="[bold cyan]POD TABLE[/bold cyan]",
            subtitle="[dim]F2[/dim]",
            border_style="bright_blue",
        )

    def watch_data(self, data: DataProvider | None) -> None:
        """Re-render when data changes."""
        self.refresh()
