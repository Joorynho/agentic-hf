"""F3 — Pod Drilldown screen (MVP3 real data)."""
from textual.widgets import Static
from textual.reactive import Reactive
from rich.panel import Panel
from rich.table import Table

from src.mission_control.data_provider import DataProvider


class PodDrilldownWidget(Static):
    """Detailed pod metrics: exposure, agent status, risk."""

    data: Reactive[DataProvider | None] = Reactive(None)
    selected_pod: str = "alpha"

    def __init__(self, data_provider: DataProvider | None = None, **kwargs):
        super().__init__(**kwargs)
        self.data = data_provider

    def render(self) -> Panel:
        if not self.data:
            return Panel(
                "[yellow]No pod data available[/yellow]",
                title="[bold cyan]POD DRILLDOWN[/bold cyan]",
                border_style="bright_blue",
            )

        summary = self.data.pod_summaries.get(self.selected_pod)
        if not summary:
            return Panel(
                f"[yellow]Pod {self.selected_pod} not found[/yellow]",
                title="[bold cyan]POD DRILLDOWN[/bold cyan]",
                border_style="bright_blue",
            )

        # Extract metrics safely from dict or PodSummary
        if isinstance(summary, dict):
            nav = summary.get('risk_metrics', {}).get('nav', 0)
            pnl = summary.get('risk_metrics', {}).get('daily_pnl', 0)
            vol = summary.get('risk_metrics', {}).get('current_vol_ann', 0)
            leverage = summary.get('risk_metrics', {}).get('gross_leverage', 0)
            exposure = summary.get('exposure_buckets', [])
            status = summary.get('status', 'UNKNOWN')
        else:
            nav = summary.risk_metrics.nav
            pnl = summary.risk_metrics.daily_pnl
            vol = summary.risk_metrics.current_vol_ann
            leverage = summary.risk_metrics.gross_leverage
            exposure = summary.exposure_buckets
            status = summary.status.value

        table = Table.grid(padding=(0, 2))
        table.add_column("Field", style="dim", width=20)
        table.add_column("Value", style="bold green")

        table.add_row("Pod ID", self.selected_pod)
        table.add_row("Status", status)
        table.add_row("NAV", f"${nav:,.0f}")
        table.add_row("Daily PnL", f"${pnl:,.0f}")
        table.add_row("Volatility", f"{vol:.2%}")
        table.add_row("Leverage", f"{leverage:.2f}x")

        if exposure:
            table.add_row("", "")  # spacer
            table.add_row("[bold]Exposure[/bold]", "")
            for exp in exposure:
                if isinstance(exp, dict):
                    table.add_row(f"  {exp.get('asset_class', '?')}", f"{exp.get('notional_pct_nav', 0):.1%}")
                else:
                    table.add_row(f"  {exp.asset_class}", f"{exp.notional_pct_nav:.1%}")

        return Panel(
            table,
            title=f"[bold cyan]POD DRILLDOWN: {self.selected_pod.upper()}[/bold cyan]",
            subtitle="[dim]F3[/dim]",
            border_style="bright_blue",
        )

    def watch_data(self, data: DataProvider | None) -> None:
        """Re-render when data changes."""
        self.refresh()
