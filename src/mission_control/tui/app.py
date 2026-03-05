"""
Agentic HF — Mission Control TUI (MVP1).

Run with:  python -m src.mission_control.tui.app

Key bindings
  F1  Firm Dashboard
  F2  Pod Table
  F8  Audit Log
  q   Quit
"""

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Header, Footer


class AgenticHFApp(App):
    """Top-level Textual application for Mission Control."""

    TITLE = "AGENTIC HF \u2014 Mission Control"
    SUB_TITLE = "MVP1"

    CSS = """
    Screen {
        background: #0a0a0a;
    }
    #firm-panel {
        border: solid #333;
        padding: 1;
        margin: 1;
    }
    .metric-label {
        color: #888;
    }
    .metric-value {
        color: #00ff88;
    }
    .status-active {
        color: #00ff88;
    }
    .status-paused {
        color: #ffaa00;
    }
    .status-halted {
        color: #ff4444;
    }
    """

    BINDINGS = [
        Binding("f1", "show_firm", "Firm Dashboard"),
        Binding("f2", "show_pods", "Pod Table"),
        Binding("f8", "show_audit", "Audit Log"),
        Binding("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        from src.mission_control.tui.screens.firm_dashboard import FirmDashboardWidget

        yield FirmDashboardWidget()
        yield Footer()

    def action_show_firm(self) -> None:
        self.query("*").remove()
        self.mount(Header(show_clock=True))
        from src.mission_control.tui.screens.firm_dashboard import FirmDashboardWidget

        self.mount(FirmDashboardWidget())
        self.mount(Footer())

    def action_show_pods(self) -> None:
        self.query("*").remove()
        self.mount(Header(show_clock=True))
        from src.mission_control.tui.screens.pod_table import PodTableWidget

        self.mount(PodTableWidget())
        self.mount(Footer())

    def action_show_audit(self) -> None:
        self.query("*").remove()
        self.mount(Header(show_clock=True))
        from src.mission_control.tui.screens.audit_screen import AuditWidget

        self.mount(AuditWidget())
        self.mount(Footer())


def run() -> None:
    """Create and run the Mission Control TUI."""
    app = AgenticHFApp()
    app.run()


if __name__ == "__main__":
    run()
