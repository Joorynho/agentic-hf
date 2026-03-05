"""F1 — Firm Dashboard screen (MVP1 demo data)."""

from textual.widgets import Static
from rich.panel import Panel
from rich.table import Table

DEMO_METRICS: dict[str, str] = {
    "NAV": "$10,241,330",
    "Daily PnL": "+$241,330 (+2.41%)",
    "Drawdown": "-1.2% from HWM",
    "Sharpe (YTD)": "1.84",
    "Vol (Ann)": "9.2%",
    "VaR 95": "1.24% NAV",
    "Gross Leverage": "1.31x",
    "Net Leverage": "0.87x",
}


class FirmDashboardWidget(Static):
    """Rich-rendered panel showing firm-level metrics."""

    def render(self) -> Panel:
        table = Table.grid(padding=(0, 3))
        table.add_column("Metric", style="dim", width=20)
        table.add_column("Value", style="bold green")
        for metric, value in DEMO_METRICS.items():
            table.add_row(metric, value)
        return Panel(
            table,
            title="[bold cyan]FIRM DASHBOARD[/bold cyan]",
            subtitle="[dim]F1[/dim]",
            border_style="bright_blue",
        )
