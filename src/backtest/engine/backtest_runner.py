from __future__ import annotations

from datetime import datetime, timedelta

from src.core.clock.simulation_clock import SimulationClock
from src.core.bus.event_bus import EventBus
from src.core.bus.audit_log import AuditLog
from src.core.models.config import PodConfig
from src.data.adapters.yfinance_adapter import YFinanceAdapter
from src.data.cache.parquet_cache import ParquetCache
from src.execution.paper.paper_adapter import PaperAdapter
from src.backtest.accounting.portfolio import PortfolioAccountant
from src.pods.base.gateway import PodGateway
from src.pods.base.namespace import PodNamespace


class BacktestRunner:
    def __init__(self, cache_dir: str, initial_nav: float = 1_000_000):
        self._cache_dir = cache_dir
        self._initial_nav = initial_nav

    async def run(self, config: PodConfig) -> dict:
        audit_log = AuditLog()
        bus = EventBus(audit_log=audit_log)
        cache = ParquetCache(self._cache_dir)
        adapter = YFinanceAdapter(cache=cache)
        accountant = PortfolioAccountant(config.pod_id, self._initial_nav)
        namespace = PodNamespace(config.pod_id)
        gateway = PodGateway(config.pod_id, bus, config)

        start_dt = datetime.combine(config.backtest.start_date, datetime.min.time())
        end_dt = datetime.combine(config.backtest.end_date, datetime.min.time())
        clock = SimulationClock(start=start_dt, end=end_dt, mode="backtest")

        # Pre-fetch all data
        all_bars: dict[str, list] = {}
        for symbol in config.universe:
            bars = await adapter.fetch(
                symbol, config.backtest.start_date, config.backtest.end_date
            )
            all_bars[symbol] = bars

        total_bars = 0
        for tick in clock:
            tick_prices = {}
            for symbol, bars in all_bars.items():
                day_bars = [b for b in bars if b.timestamp.date() == tick.date()]
                for bar in day_bars:
                    await gateway.push_bar(bar)
                    tick_prices[symbol] = bar.close
                    total_bars += 1
            if tick_prices:
                accountant.mark_to_market(tick_prices)

        return {
            "nav_final": accountant.nav,
            "drawdown_from_hwm": accountant.drawdown_from_hwm(),
            "total_bars_processed": total_bars,
            "pod_id": config.pod_id,
        }
