"""F3 — Pod Drill-Down screen.

Shows exposure buckets, agent status, risk metrics, and last collaboration loop
for a single selected pod. Activated by pressing Enter on a pod row in F2.
"""
from __future__ import annotations

from textual.widgets import DataTable, Static
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box


POD_DATA = {
    "alpha": {
        "strategy": "MOMENTUM", "status": "ACTIVE", "nav": 2_341_200,
        "pnl": 41_200, "pnl_pct": 1.79,
        "vol": 9.4, "dd": 3.2, "var": 1.1, "leverage": 1.2,
        "exposure": [("US Equity Large-Cap", 82), ("Cash", 18)],
        "agents": [
            ("Researcher", "OK", "0.3s"),
            ("Signal", "OK", "0.1s"),
            ("PM", "OK", "0.2s"),
            ("Risk", "OK", "0.1s"),
            ("Exec Trader", "OK", "0.4s"),
            ("Ops", "OK", "1.0s"),
        ],
        "last_loop": ("PM→Risk", 5, True, "0.8s"),
        "poly_signals": [],
    },
    "beta": {
        "strategy": "STAT ARB", "status": "ACTIVE", "nav": 1_980_500,
        "pnl": 12_300, "pnl_pct": 0.62,
        "vol": 6.1, "dd": 1.8, "var": 0.8, "leverage": 1.7,
        "exposure": [("US Sector ETFs", 75), ("Cash", 25)],
        "agents": [
            ("Researcher", "OK", "0.5s"),
            ("Signal", "OK", "0.2s"),
            ("PM", "OK", "0.3s"),
            ("Risk", "OK", "0.1s"),
            ("Exec Trader", "OK", "0.6s"),
            ("Ops", "OK", "1.2s"),
        ],
        "last_loop": ("PM→Risk", 3, True, "0.5s"),
        "poly_signals": [],
    },
    "gamma": {
        "strategy": "MACRO", "status": "ACTIVE", "nav": 2_100_000,
        "pnl": 18_500, "pnl_pct": 0.88,
        "vol": 8.9, "dd": 4.1, "var": 1.4, "leverage": 1.1,
        "exposure": [("Multi-Asset", 90), ("Cash", 10)],
        "agents": [
            ("Researcher", "OK", "0.8s"),
            ("Signal", "OK", "0.3s"),
            ("PM (LLM)", "OK", "1.2s"),
            ("Risk", "OK", "0.2s"),
            ("Exec Trader", "OK", "0.7s"),
            ("Ops", "OK", "1.5s"),
        ],
        "last_loop": ("Signal→PM", 4, True, "1.1s"),
        "poly_signals": ["Fed cut 65% prob", "Election odds shifting"],
    },
    "delta": {
        "strategy": "EVENT", "status": "ACTIVE", "nav": 1_750_000,
        "pnl": -5_200, "pnl_pct": -0.30,
        "vol": 11.2, "dd": 9.8, "var": 2.1, "leverage": 0.9,
        "exposure": [("US Equities", 85), ("Cash", 15)],
        "agents": [
            ("Researcher", "OK", "1.0s"),
            ("Signal", "OK", "0.4s"),
            ("PM (LLM)", "OK", "1.5s"),
            ("Risk", "OK", "0.2s"),
            ("Exec Trader", "OK", "0.8s"),
            ("Ops", "OK", "1.8s"),
        ],
        "last_loop": ("PM→Risk", 8, True, "1.3s"),
        "poly_signals": ["AAPL earnings 72% beat prob"],
    },
    "epsilon": {
        "strategy": "VOL REGIME", "status": "ACTIVE", "nav": 1_900_000,
        "pnl": 22_800, "pnl_pct": 1.20,
        "vol": 7.3, "dd": 2.1, "var": 1.0, "leverage": 1.3,
        "exposure": [("VIX Products", 60), ("SPY Hedge", 20), ("Cash", 20)],
        "agents": [
            ("Researcher", "OK", "0.6s"),
            ("Signal", "OK", "0.2s"),
            ("PM", "OK", "0.3s"),
            ("Risk", "OK", "0.1s"),
            ("Exec Trader", "OK", "0.5s"),
            ("Ops", "OK", "1.1s"),
        ],
        "last_loop": ("Researcher→Signal", 2, True, "0.4s"),
        "poly_signals": ["VIX event 45% prob >30"],
    },
}


class PodDrilldownWidget(Static):
    """F3 pod drill-down — shows full detail for one pod."""

    def __init__(self, pod_id: str = "alpha") -> None:
        super().__init__()
        self._pod_id = pod_id

    def render(self) -> Panel:
        data = POD_DATA.get(self._pod_id, POD_DATA["alpha"])
        pnl_sign = "+" if data["pnl"] >= 0 else ""
        pnl_color = "green" if data["pnl"] >= 0 else "red"

        # Header
        header = Text()
        header.append(f"  NAV: ${data['nav']:,.0f}  │  ", style="bold white")
        header.append(f"PnL: {pnl_sign}${data['pnl']:,.0f} ({pnl_sign}{data['pnl_pct']:.2f}%)  │  ",
                      style=f"bold {pnl_color}")
        status_color = "green" if data["status"] == "ACTIVE" else "yellow"
        header.append(f"Status: ● {data['status']}", style=f"bold {status_color}")

        # Left: Exposure + Risk
        left = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
        left.add_column("Key", style="dim")
        left.add_column("Val", style="cyan")

        left.add_row("[bold]EXPOSURE BUCKETS[/bold]", "")
        for name, pct in data["exposure"]:
            left.add_row(f"  {name}", f"{pct}%")

        left.add_row("", "")
        left.add_row("[bold]RISK METRICS[/bold]", "")
        dd_color = "red" if data["dd"] > 8 else ("yellow" if data["dd"] > 5 else "green")
        var_color = "red" if data["var"] > 1.8 else "green"
        left.add_row("  Vol (ann):", f"{data['vol']:.1f}%")
        left.add_row("  Drawdown:", f"[{dd_color}]{data['dd']:.1f}%[/{dd_color}]")
        left.add_row("  VaR 95%:", f"[{var_color}]{data['var']:.1f}%[/{var_color}]")
        left.add_row("  Leverage:", f"{data['leverage']:.1f}x")

        # Right: Agent status
        right = Table(box=box.SIMPLE, show_header=True, padding=(0, 1))
        right.add_column("Agent", style="bold")
        right.add_column("Status")
        right.add_column("Last beat")
        for agent, status, last in data["agents"]:
            dot = "[green]●[/green]" if status == "OK" else "[red]✗[/red]"
            right.add_row(f"{dot} {agent}", f"[green]{status}[/green]", last)

        # Loop summary
        loop_name, iters, consensus, duration = data["last_loop"]
        consensus_str = "[green]✓[/green]" if consensus else "[red]✗[/red]"
        loop_line = (
            f"  [dim]Last loop:[/dim] {loop_name}  "
            f"[dim]iters:[/dim] {iters}  "
            f"[dim]consensus:[/dim] {consensus_str}  "
            f"[dim]time:[/dim] {duration}"
        )

        # Polymarket signals
        poly_lines = ""
        if data["poly_signals"]:
            poly_lines = "\n  [bold magenta]POLYMARKET:[/bold magenta] " + "  │  ".join(
                f"[magenta]{s}[/magenta]" for s in data["poly_signals"]
            )

        from rich.columns import Columns
        from rich.console import Group
        body = Group(header, Columns([left, right]), Text(loop_line), Text(poly_lines))
        return Panel(body, title=f"[bold cyan]POD DRILL-DOWN: {self._pod_id.upper()} [{data['strategy']}][/bold cyan]",
                     border_style="cyan")
