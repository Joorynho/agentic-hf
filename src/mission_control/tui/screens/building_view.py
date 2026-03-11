"""F9 — Building View with live agent heartbeats."""
from __future__ import annotations

from textual.widgets import Static
from textual.reactive import Reactive

from src.mission_control.data_provider import DataProvider


POD_IDS = ["equities", "fx", "crypto", "commodities"]


class BuildingViewWidget(Static):
    """Animated ASCII building with live pod status indicators."""

    data: Reactive[DataProvider | None] = Reactive(None)

    def __init__(self, data_provider: DataProvider | None = None, **kwargs):
        super().__init__(**kwargs)
        self.data = data_provider
        self._tick = 0

    def on_mount(self) -> None:
        self.set_interval(2.0, self._refresh_tick)

    def _refresh_tick(self) -> None:
        self._tick += 1
        self.refresh()

    def _pod_indicator(self, pod_id: str) -> str:
        """Return a colored dot for pod status."""
        if self.data is None:
            return "[dim]○[/dim]"
        summaries = self.data.pod_summaries
        summary = summaries.get(pod_id)
        if summary is None:
            return "[dim]○[/dim]"

        risk_halt = False
        has_positions = False
        nav = 0.0

        if isinstance(summary, dict):
            rm = summary.get("risk_metrics", {})
            nav = rm.get("nav", 0.0) if isinstance(rm, dict) else summary.get("nav", 0.0)
            positions = summary.get("positions", [])
            has_positions = len(positions) > 0
            risk_halt = summary.get("risk_halt", False)
        else:
            nav = summary.risk_metrics.nav if hasattr(summary, "risk_metrics") else 0.0
            has_positions = bool(getattr(summary, "positions", []))
            risk_halt = getattr(summary, "risk_halt", False)

        if risk_halt:
            return "[red]●[/red]"
        elif has_positions or nav > 0:
            return "[green]●[/green]"
        else:
            pulse = "●" if self._tick % 2 == 0 else "○"
            return f"[yellow]{pulse}[/yellow]"

    def _gov_indicator(self, role: str) -> str:
        """Return colored dot for governance agent."""
        if self.data is None:
            return "[dim]○[/dim]"
        if self.data.firm_nav > 0:
            return "[green]●[/green]"
        pulse = "●" if self._tick % 3 == 0 else "○"
        return f"[cyan]{pulse}[/cyan]"

    def _firm_stats(self) -> str:
        if self.data is None:
            return "NAV: --  PnL: --"
        nav = self.data.firm_nav
        pnl = self.data.firm_daily_pnl
        pnl_color = "green" if pnl >= 0 else "red"
        return f"NAV: [bold]${nav:,.0f}[/bold]  PnL: [{pnl_color}]${pnl:+,.0f}[/{pnl_color}]"

    def render(self) -> str:
        ei = self._pod_indicator("equities")
        fi = self._pod_indicator("fx")
        ci = self._pod_indicator("crypto")
        coi = self._pod_indicator("commodities")

        ceo = self._gov_indicator("CEO")
        cio = self._gov_indicator("CIO")
        cro = self._gov_indicator("CRO")

        stats = self._firm_stats()

        building = f"""
        {stats}

        ╔══════════════════════╗
        ║ {ceo} CEO              ║  Floor 5: Governance
        ║ {cio} CIO              ║  (strategy, allocation)
        ║ {cro} CRO              ║
        ╠══════════════════════╣
        ║ {ei} Equities    ║  Floor 4: Pods
        ║ {fi} FX          ║  (execution,
        ║ {ci} Crypto      ║   risk metrics)
        ║ {coi} Commodities ║
        ╠══════════════════════╣
        ║ [cyan]◆ EventBus[/cyan]        ║  Floor 3: Bus
        ║ [cyan]◆ AuditLog[/cyan]        ║  (event flow)
        ╠══════════════════════╣
        ║ [yellow]≈ Data Cache[/yellow]      ║  Floor 2: State
        ║ [yellow]≈ Positions[/yellow]       ║  (live metrics)
        ╠══════════════════════╣
        ║ [blue]⚙ Alpaca[/blue]         ║  Floor 1: Market
        ║ [blue]⚙ API Layer[/blue]      ║  (bars, orders)
        ╚══════════════════════╝
        """
        return building

    def watch_data(self, data: DataProvider | None) -> None:
        self.refresh()
