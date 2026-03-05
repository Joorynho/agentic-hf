"""F8 — Audit Log screen (MVP1 demo data)."""

from textual.widgets import DataTable

DEMO_AUDIT: list[tuple[str, ...]] = [
    ("14:32:07", "risk_manager", "HALT", "pod.delta", "drawdown -5.8% exceeds limit"),
    ("14:28:12", "cio", "REBALANCE", "pod.alpha", "monthly capital review +2%"),
    ("14:21:45", "system", "POD_STARTED", "pod.epsilon", "vol regime pod initialized"),
    ("14:15:03", "data_feed", "DATA_ALERT", "yfinance", "TSLA bar missing 14:00"),
    ("14:00:00", "system", "BACKTEST_START", "firm", "MVP1 simulation started"),
]


class AuditWidget(DataTable):
    """DataTable showing the audit event stream."""

    def on_mount(self) -> None:
        self.add_columns("Time", "Actor", "Action", "Target", "Detail")
        for row in DEMO_AUDIT:
            self.add_row(*row)
