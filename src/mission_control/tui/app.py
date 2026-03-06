"""
Agentic HF -- Mission Control TUI (MVP2).

Run with:  python -m src.mission_control.tui.app

Key bindings: F1 Firm | F2 Pods | F3 Drill-Down | F5 Risk | F6 Control | F8 Audit | F9 Building | q Quit
"""

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Header, Footer


class AgenticHFApp(App):
    TITLE = "AGENTIC HF -- Mission Control"
    SUB_TITLE = "MVP2"

    CSS = """
    Screen { background: #0a0a0a; }
    #firm-panel { border: solid #333; padding: 1; margin: 1; }
    .metric-label { color: #888; }
    .metric-value { color: #00ff88; }
    .status-active { color: #00ff88; }
    .status-paused { color: #ffaa00; }
    .status-halted { color: #ff4444; }
    """

    BINDINGS = [
        Binding("f1", "show_firm", "Firm Dashboard"),
        Binding("f2", "show_pods", "Pod Table"),
        Binding("f3", "show_drilldown", "Pod Drill-Down"),
        Binding("f5", "show_risk", "Risk Limits"),
        Binding("f6", "show_control", "Control Plane"),
        Binding("f8", "show_audit", "Audit Log"),
        Binding("f9", "show_building", "Building View"),
        Binding("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        from src.mission_control.tui.screens.firm_dashboard import FirmDashboardWidget
        yield FirmDashboardWidget()
        yield Footer()

    def _swap(self, widget) -> None:
        self.query("*").remove()
        self.mount(Header(show_clock=True))
        self.mount(widget)
        self.mount(Footer())

    def action_show_firm(self) -> None:
        from src.mission_control.tui.screens.firm_dashboard import FirmDashboardWidget
        self._swap(FirmDashboardWidget())

    def action_show_pods(self) -> None:
        from src.mission_control.tui.screens.pod_table import PodTableWidget
        self._swap(PodTableWidget())

    def action_show_drilldown(self) -> None:
        from src.mission_control.tui.screens.pod_drilldown import PodDrilldownWidget
        self._swap(PodDrilldownWidget("alpha"))

    def action_show_risk(self) -> None:
        from src.mission_control.tui.screens.risk_limits import RiskLimitsWidget
        self._swap(RiskLimitsWidget())

    def action_show_control(self) -> None:
        from src.mission_control.tui.screens.control_plane import ControlPlaneWidget
        self._swap(ControlPlaneWidget())

    def action_show_audit(self) -> None:
        from src.mission_control.tui.screens.audit_screen import AuditWidget
        self._swap(AuditWidget())

    def action_show_building(self) -> None:
        from src.mission_control.tui.screens.building_view import BuildingViewWidget
        self._swap(BuildingViewWidget())


def run() -> None:
    app = AgenticHFApp()
    app.run()


if __name__ == "__main__":
    run()
