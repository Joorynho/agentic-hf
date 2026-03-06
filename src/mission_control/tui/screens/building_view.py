"""F9 — Building View (MVP3 real data)."""
from textual.widgets import Static
from textual.reactive import Reactive

from src.mission_control.data_provider import DataProvider


class BuildingViewWidget(Static):
    """Animated ASCII building with agent activity heartbeats."""

    data: Reactive[DataProvider | None] = Reactive(None)

    def __init__(self, data_provider: DataProvider | None = None, **kwargs):
        super().__init__(**kwargs)
        self.data = data_provider

    def render(self) -> str:
        # Existing ASCII building code (unchanged)
        building = """
        ╔══════════════════╗
        ║ [red]● CEO[/red]         ║  Floor 5: Governance
        ║ ● CIO           ║  (strategy, allocation)
        ║ ● CRO           ║
        ╠══════════════════╣
        ║ [green]●[/green] Alpha      ║  Floor 4: Pods
        ║ [green]●[/green] Beta       ║  (execution,
        ║ [green]●[/green] Gamma      ║   risk metrics)
        ║ [green]●[/green] Delta      ║
        ║ [green]●[/green] Epsilon    ║
        ╠══════════════════╣
        ║ [cyan]◆ EventBus[/cyan]    ║  Floor 3: Bus
        ║ [cyan]◆ AuditLog[/cyan]    ║  (event flow)
        ╠══════════════════╣
        ║ [yellow]≈ Data Cache[/yellow]  ║  Floor 2: State
        ║ [yellow]≈ Positions[/yellow]   ║  (live metrics)
        ╠══════════════════╣
        ║ [blue]⚙ Alpaca[/blue]     ║  Floor 1: Market
        ║ [blue]⚙ API Layer[/blue]   ║  (bars, orders)
        ╚══════════════════╝
        """
        return building

    def watch_data(self, data: DataProvider | None) -> None:
        """Re-render when data changes."""
        self.refresh()
