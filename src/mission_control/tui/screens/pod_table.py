"""F2 — Pod Table screen (MVP1 demo data)."""

from textual.widgets import DataTable

DEMO_PODS: list[tuple[str, ...]] = [
    ("Alpha", "Momentum", "ACTIVE", "+$84,210", "+0.82%", "9.1%", "-1.2%", "20.0%"),
    ("Beta", "Stat Arb", "ACTIVE", "+$62,100", "+0.61%", "7.8%", "-0.8%", "18.5%"),
    ("Gamma", "Macro", "ACTIVE", "+$55,900", "+0.55%", "10.2%", "-2.1%", "25.0%"),
    ("Delta", "Event", "PAUSED", "+$21,400", "+0.21%", "14.1%", "-5.8%", "16.5%"),
    ("Epsilon", "Vol", "ACTIVE", "+$17,720", "+0.17%", "9.8%", "-1.4%", "20.0%"),
]


class PodTableWidget(DataTable):
    """DataTable listing every pod with key metrics."""

    def on_mount(self) -> None:
        self.add_columns(
            "Pod", "Strategy", "Status", "Daily PnL",
            "PnL%", "Vol", "Drawdown", "Capital%",
        )
        for row in DEMO_PODS:
            self.add_row(*row)
