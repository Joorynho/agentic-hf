"""F1 — Firm Dashboard screen (MVP3 real data)."""

from textual.widgets import Static
from textual.reactive import Reactive
from rich.panel import Panel
from rich.table import Table

from src.mission_control.data_provider import DataProvider


class FirmDashboardWidget(Static):
    """Real-time firm metrics via DataProvider."""

    # Reactive properties trigger re-render on change
    data: Reactive[DataProvider | None] = Reactive(None)

    def __init__(self, data_provider: DataProvider | None = None, **kwargs):
        super().__init__(**kwargs)
        self.data = data_provider

    def render(self) -> Panel:
        if not self.data:
            return Panel(
                "[yellow]Waiting for DataProvider...[/yellow]",
                title="[bold cyan]FIRM DASHBOARD[/bold cyan]",
                border_style="bright_blue",
            )

        # Build live metrics from DataProvider
        nav = self.data.firm_nav
        daily_pnl = self.data.firm_daily_pnl
        pnl_pct = (daily_pnl / nav * 100) if nav > 0 else 0.0

        metrics = {
            "NAV": f"${nav:,.2f}",
            "Daily PnL": f"+${daily_pnl:,.2f} (+{pnl_pct:.2f}%)" if daily_pnl >= 0 else f"-${abs(daily_pnl):,.2f} ({pnl_pct:.2f}%)",
            "Active Pods": str(len(self.data.pod_summaries)),
        }

        # Add pod-level aggregates if available
        if self.data.pod_summaries:
            summaries = list(self.data.pod_summaries.values())
            avg_drawdown = sum(s.get('risk_metrics', {}).get('drawdown_from_hwm', 0) for s in summaries) / len(summaries)
            avg_vol = sum(s.get('risk_metrics', {}).get('current_vol_ann', 0) for s in summaries) / len(summaries)
            total_var = sum(s.get('risk_metrics', {}).get('var_95_1d', 0) for s in summaries)
            avg_leverage = sum(s.get('risk_metrics', {}).get('gross_leverage', 0) for s in summaries) / len(summaries)

            metrics.update({
                "Avg Drawdown": f"{avg_drawdown:.2%}",
                "Avg Vol": f"{avg_vol:.2%}",
                "Total VaR": f"{total_var:.3f}",
                "Avg Leverage": f"{avg_leverage:.2f}x",
            })

        table = Table.grid(padding=(0, 3))
        table.add_column("Metric", style="dim", width=20)
        table.add_column("Value", style="bold green")
        for metric, value in metrics.items():
            table.add_row(metric, value)

        return Panel(
            table,
            title="[bold cyan]FIRM DASHBOARD[/bold cyan]",
            subtitle="[dim]F1[/dim]",
            border_style="bright_blue",
        )

    def watch_data(self, data: DataProvider | None) -> None:
        """Re-render when DataProvider updates."""
        if data is not None:
            self.refresh()
