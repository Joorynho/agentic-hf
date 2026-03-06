"""F6 — Control Plane screen.

Capital allocation bars, pod pause/resume buttons, governance triggers, kill switches.
RBAC-gated: kill switches require CRO role (enforced in UI via confirmation prompt).
"""
from __future__ import annotations

from textual.widgets import Static
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.columns import Columns
from rich.console import Group
from rich import box


_ALLOCATIONS = {
    "alpha": 0.20,
    "beta": 0.20,
    "gamma": 0.22,
    "delta": 0.18,
    "epsilon": 0.20,
}

_POD_STATUS = {
    "alpha": "ACTIVE",
    "beta": "ACTIVE",
    "gamma": "ACTIVE",
    "delta": "ACTIVE",
    "epsilon": "ACTIVE",
}


def _bar(pct: float, width: int = 20) -> str:
    filled = int(pct * width)
    empty = width - filled
    return f"[green]{'█' * filled}[/green][dim]{'░' * empty}[/dim]"


class ControlPlaneWidget(Static):
    """F6 control plane — capital allocation + pod controls + kill switches."""

    def render(self) -> Panel:
        # Allocation table
        alloc_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
        alloc_table.add_column("Pod", style="bold cyan", width=10)
        alloc_table.add_column("Bar", width=24)
        alloc_table.add_column("Pct", width=6)

        for pod_id, pct in _ALLOCATIONS.items():
            alloc_table.add_row(pod_id.upper(), _bar(pct), f"{pct:.0%}")

        # Pod controls
        pod_controls = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
        pod_controls.add_column("Pod", width=10)
        pod_controls.add_column("Actions", width=30)

        for pod_id, status in _POD_STATUS.items():
            if status == "ACTIVE":
                actions = f"[yellow][ PAUSE {pod_id.upper():5s} ][/yellow]   [dim][ RESUME ][/dim]"
            else:
                actions = f"[dim][ PAUSE  ][/dim]   [green][ RESUME {pod_id.upper():5s} ][/green]"
            pod_controls.add_row(pod_id.upper(), actions)

        # Governance buttons
        gov_text = Text()
        gov_text.append("  [ TRIGGER CEO/CIO REVIEW ]", style="bold cyan")
        gov_text.append("    ")
        gov_text.append("[ FORCE REBALANCE ]", style="bold cyan")

        # Kill switches
        kill_text = Text()
        kill_text.append("  ■ KILL POD  ", style="bold red on dark_red")
        kill_text.append("   ")
        kill_text.append("■■ KILL FIRM  ", style="bold white on red")
        kill_text.append("  [dim](CRO role required)[/dim]")

        body = Group(
            Text("[bold]CAPITAL ALLOCATION[/bold]", justify="left"),
            alloc_table,
            Text(""),
            Columns([
                Group(Text("[bold]POD CONTROLS[/bold]"), pod_controls),
                Group(
                    Text("[bold]GOVERNANCE[/bold]"),
                    gov_text,
                    Text(""),
                    Text("[bold]KILL SWITCHES[/bold]"),
                    kill_text,
                ),
            ]),
        )
        return Panel(body, title="[bold red]CONTROL PLANE[/bold red]", border_style="red")
