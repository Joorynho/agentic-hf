"""F9 — Building View screen.

Animated ASCII building: each floor is a pod, penthouse is CEO/CIO/CRO.
Updates every second via Textual Timer. Agent dots pulse on activity.
Risk profile shown per floor (V/DD/L), color-coded vs limits.
"""
from __future__ import annotations

import time

from textual.reactive import reactive
from textual.widgets import Static
from rich.panel import Panel
from rich.text import Text
from rich.console import Group


_FLOOR_DATA = [
    # (pod_id, strategy, vol, vol_lim, dd, dd_lim, lev, lev_lim, pnl, status)
    ("EPSILON", "VOL",   7.3, 10.0, 2.1, 9.0,  1.3, 1.5,  "+1.2%", "active"),
    ("DELTA",   "EVENT", 11.2,15.0, 9.8,12.0,  0.9, 1.0,  "-0.3%", "active"),
    ("GAMMA",   "MACRO", 8.9, 10.0, 4.1, 8.0,  1.1, 1.2,  "+0.8%", "active"),
    ("BETA",    "PAIRS", 6.1, 8.0,  1.8, 7.0,  1.7, 2.0,  "+0.5%", "active"),
    ("ALPHA",   "MOM",   9.4, 12.0, 3.2,10.0,  1.2, 1.5,  "+1.8%", "active"),
]

_DATA_FEEDS = [
    ("yfinance", True),
    ("FRED", True),
    ("GDELT", True),
    ("Polymarket", True),
]


def _metric_color(actual: float, limit: float) -> str:
    pct = actual / limit if limit else 0
    if pct > 0.90:
        return "red"
    if pct > 0.70:
        return "yellow"
    return "green"


def _risk_str(vol, vl, dd, dl, lev, ll) -> Text:
    t = Text()
    t.append("V:", style="dim")
    vc = _metric_color(vol, vl)
    t.append(f"{vol:.1f}%", style=vc)
    t.append(" DD:", style="dim")
    dc = _metric_color(dd, dl)
    t.append(f"{dd:.1f}%", style=dc)
    if dd / dl > 0.90:
        t.append("⚠", style="bold red")
    t.append(" L:", style="dim")
    lc = _metric_color(lev, ll)
    t.append(f"{lev:.1f}x", style=lc)
    return t


class BuildingViewWidget(Static):
    """F9 animated building view. Refreshes every second."""

    tick: reactive[int] = reactive(0)

    def on_mount(self) -> None:
        self.set_interval(1, self._tick)

    def _tick(self) -> None:
        self.tick += 1

    def watch_tick(self, value: int) -> None:  # noqa: ARG002
        self.refresh()

    def render(self) -> Panel:
        t = self.tick
        lines: list[Text] = []

        # Penthouse — CEO/CIO/CRO
        ceo_active = (t % 3) != 0
        cio_active = (t % 4) != 1
        cro_active = True
        ceo_dot = "[bold green]●[/bold green]" if ceo_active else "[dim]○[/dim]"
        cio_dot = "[bold green]●[/bold green]" if cio_active else "[dim]○[/dim]"
        cro_dot = "[bold green]●[/bold green]" if cro_active else "[dim]○[/dim]"

        # Collaboration loop indicator
        in_loop = (t % 8) < 3
        if in_loop:
            loop_iter = (t % 3) + 1
            loop_bar = "●" * loop_iter + "○" * (5 - loop_iter)
            loop_str = f" [bold cyan][deliberating iter {loop_iter}/5 {loop_bar}][/bold cyan]"
        else:
            loop_str = ""

        penthouse = Text()
        penthouse.append("  ╔═══════════════════════════════════════════════════════╗\n", style="bold blue")
        penthouse.append("  ║  PENTHOUSE  │  ", style="bold blue")
        penthouse.append("👑 CEO ", style="bold yellow")
        penthouse.append(ceo_dot)
        penthouse.append("  🧠 CIO ", style="bold cyan")
        penthouse.append(cio_dot)
        penthouse.append("  🛡 CRO ", style="bold red")
        penthouse.append(cro_dot)
        penthouse.append(loop_str)
        penthouse.append("\n  ╠═══════════════════════════════════════════════════════╣\n", style="bold blue")
        lines.append(penthouse)

        # Floors (top = floor 5 = epsilon)
        for floor_num, (pod, strategy, vol, vl, dd, dl, lev, ll, pnl, status) in enumerate(
            _FLOOR_DATA, start=1
        ):
            # Agent dots: 6 per pod, pulse based on tick
            dots = Text()
            for i in range(6):
                active = ((t + i * 2) % 5) != 0
                if status == "halted":
                    dots.append("✗", style="bold red")
                elif active:
                    dots.append("●", style="bold green")
                else:
                    dots.append("○", style="dim")

            pnl_color = "green" if pnl.startswith("+") else "red"
            floor_line = Text()
            floor_line.append(f"  ║  FL{len(_FLOOR_DATA) - floor_num + 1} │ ", style="bold blue")
            floor_line.append(f"{pod:7s}", style="bold white")
            floor_line.append(f"[{strategy:5s}]  ", style="dim")
            floor_line.append(dots)
            floor_line.append(f"  PnL ", style="dim")
            floor_line.append(pnl, style=f"bold {pnl_color}")
            floor_line.append("  │  ")
            floor_line.append(_risk_str(vol, vl, dd, dl, lev, ll))
            floor_line.append("\n  ╠═══════════════════════════════════════════════════════╣\n",
                               style="bold blue")
            lines.append(floor_line)

        # Capital flow indicator (right side)
        flow_up = (t % 6) < 3
        flow_char = "▲ $" if flow_up else "  "
        flow_note = Text(f"  {flow_char} capital flow", style="bold cyan" if flow_up else "dim")
        lines.append(flow_note)

        # Basement — data feeds
        basement = Text()
        basement.append("  ║  BASEMENT  │  ", style="bold blue")
        for feed, healthy in _DATA_FEEDS:
            dot = "[green]●[/green]" if healthy else "[red]✗[/red]"
            basement.append(f"{feed} ")
            basement.append(dot)
            basement.append("  ")
        basement.append("\n  ╚═══════════════════════════════════════════════════════╝\n",
                         style="bold blue")
        lines.append(basement)

        body = Group(*lines)
        return Panel(
            body,
            title="[bold green]AGENTIC HEDGE FUND — LIVE[/bold green]",
            border_style="green",
        )
