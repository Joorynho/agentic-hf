"""F5 — Risk Limits screen.

Live actuals vs limits for all 5 pods + firm aggregate row.
Green < 70% of limit, Yellow 70-90%, Red > 90% (blinking).
"""
from __future__ import annotations

from textual.widgets import DataTable, Static
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box


# (actual, limit)
_RISK_DATA = {
    "alpha":   {"vol": (9.4, 12.0),  "dd": (3.2, 10.0),  "lev": (1.2, 1.5), "var": (1.1, 2.0)},
    "beta":    {"vol": (6.1, 8.0),   "dd": (1.8, 7.0),   "lev": (1.7, 2.0), "var": (0.8, 1.5)},
    "gamma":   {"vol": (8.9, 10.0),  "dd": (4.1, 8.0),   "lev": (1.1, 1.2), "var": (1.4, 2.0)},
    "delta":   {"vol": (11.2, 15.0), "dd": (9.8, 12.0),  "lev": (0.9, 1.0), "var": (2.1, 2.5)},
    "epsilon": {"vol": (7.3, 10.0),  "dd": (2.1, 9.0),   "lev": (1.3, 1.5), "var": (1.0, 2.0)},
}
_FIRM = {"var": (2.1, 3.0), "lev": (1.2, 1.5)}


def _color(actual: float, limit: float) -> str:
    pct = actual / limit if limit else 0
    if pct > 0.90:
        return "bold red"
    if pct > 0.70:
        return "bold yellow"
    return "green"


def _cell(actual: float, limit: float, suffix: str = "%") -> str:
    color = _color(actual, limit)
    warn = " ⚠" if actual / limit > 0.90 else ""
    return f"[{color}]{actual:.1f}{suffix}/{limit:.1f}{suffix}{warn}[/{color}]"


class RiskLimitsWidget(Static):
    """F5 risk limits table — all 5 pods + firm row."""

    def render(self) -> Panel:
        t = Table(box=box.SIMPLE_HEAD, show_header=True, padding=(0, 1), expand=True)
        t.add_column("Pod", style="bold cyan", width=10)
        t.add_column("Vol act/lim", width=16)
        t.add_column("DD act/lim", width=16)
        t.add_column("Lev act/lim", width=16)
        t.add_column("VaR act/lim", width=16)
        t.add_column("⚠", width=3)

        for pod_id, d in _RISK_DATA.items():
            v, dd, lev, var = d["vol"], d["dd"], d["lev"], d["var"]
            alerts = sum(1 for a, lim in [v, dd, lev, var] if a / lim > 0.90)
            alert_str = f"[red]{'!' * alerts}[/red]" if alerts else ""
            t.add_row(
                pod_id.upper(),
                _cell(*v),
                _cell(*dd),
                _cell(*lev, suffix="x"),
                _cell(*var),
                alert_str,
            )

        # Firm row
        t.add_section()
        t.add_row(
            "[bold white]FIRM[/bold white]",
            "",
            "",
            _cell(*_FIRM["lev"], suffix="x"),
            _cell(*_FIRM["var"]),
            "",
        )

        return Panel(t, title="[bold yellow]RISK LIMITS — ACTUALS vs HARD LIMITS[/bold yellow]",
                     border_style="yellow")
