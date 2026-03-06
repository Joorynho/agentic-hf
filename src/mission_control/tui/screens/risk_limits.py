"""F5 — Risk Limits screen (MVP3 real data)."""
from textual.widgets import Static
from textual.reactive import Reactive
from rich.panel import Panel
from rich.table import Table

from src.mission_control.data_provider import DataProvider


class RiskLimitsWidget(Static):
    """Risk metrics with color-coded thresholds."""

    data: Reactive[DataProvider | None] = Reactive(None)

    def __init__(self, data_provider: DataProvider | None = None, **kwargs):
        super().__init__(**kwargs)
        self.data = data_provider

    def render(self) -> Panel:
        if not self.data or not self.data.pod_summaries:
            return Panel(
                "[yellow]No pod data available[/yellow]",
                title="[bold cyan]RISK LIMITS[/bold cyan]",
                border_style="bright_blue",
            )

        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Pod", style="cyan", width=10)
        table.add_column("Drawdown", width=15)
        table.add_column("Leverage", width=15)
        table.add_column("VaR", width=15)
        table.add_column("Vol", width=15)

        for pod_id, summary in self.data.pod_summaries.items():
            if isinstance(summary, dict):
                dd = summary.get('risk_metrics', {}).get('drawdown_from_hwm', 0.0)
                lev = summary.get('risk_metrics', {}).get('gross_leverage', 0.0)
                var = summary.get('risk_metrics', {}).get('var_95_1d', 0.0)
                vol = summary.get('risk_metrics', {}).get('current_vol_ann', 0.0)
            else:
                dd = summary.risk_metrics.drawdown_from_hwm
                lev = summary.risk_metrics.gross_leverage
                var = summary.risk_metrics.var_95_1d
                vol = summary.risk_metrics.current_vol_ann

            # Color code: <70%=green, 70-90%=yellow, >90%=red of limit
            dd_color = "green" if dd < 0.07 else "yellow" if dd < 0.09 else "red"
            lev_color = "green" if lev < 1.4 else "yellow" if lev < 1.8 else "red"
            var_color = "green" if var < 0.015 else "yellow" if var < 0.020 else "red"
            vol_color = "green" if vol < 0.10 else "yellow" if vol < 0.15 else "red"

            table.add_row(
                pod_id,
                f"[{dd_color}]{dd:.2%}[/{dd_color}]",
                f"[{lev_color}]{lev:.2f}x[/{lev_color}]",
                f"[{var_color}]{var:.3f}[/{var_color}]",
                f"[{vol_color}]{vol:.2%}[/{vol_color}]",
            )

        return Panel(
            table,
            title="[bold cyan]RISK LIMITS[/bold cyan]",
            subtitle="[dim]F5[/dim]",
            border_style="bright_blue",
        )

    def watch_data(self, data: DataProvider | None) -> None:
        """Re-render when data changes."""
        self.refresh()
