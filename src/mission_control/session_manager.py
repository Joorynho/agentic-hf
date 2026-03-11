"""Live paper trading session manager — orchestrate pods, governance, and logging."""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load .env file at module import time
_env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(str(_env_path))

from src.agents.ceo.ceo_agent import CEOAgent
from src.agents.cio.cio_agent import CIOAgent
from src.agents.governance.governance_orchestrator import GovernanceOrchestrator
from src.agents.risk.cro_agent import CROAgent
from src.backtest.accounting.capital_allocator import CapitalAllocator
from src.backtest.accounting.portfolio import PortfolioAccountant
from src.core.bus.audit_log import AuditLog
from src.core.bus.event_bus import EventBus
from src.data.adapters.fred_adapter import FredAdapter
from src.data.adapters.gdelt_adapter import GdeltAdapter
from src.data.adapters.market_tracker import MarketTracker
from src.data.adapters.polymarket_adapter import PolymarketAdapter
from src.data.adapters.rss_adapter import RssAdapter
from src.data.adapters.x_adapter import XAdapter
from src.data.adapters.price_service import PriceService
from src.data.adapters.stockprices_adapter import StockPricesAdapter
from src.data.adapters.coinmarketcap_adapter import CoinMarketCapAdapter
from src.data.adapters.alphavantage_adapter import AlphaVantageAdapter
from src.core.models.allocation import MandateUpdate
from src.core.models.market import Bar
from src.core.models.config import PodConfig, RiskBudget, ExecutionConfig, BacktestConfig
from src.core.models.enums import TimeHorizon, AgentType
from src.core.models.messages import AgentMessage
from src.core.models.pod_summary import PodSummary
from src.execution.paper.alpaca_adapter import AlpacaAdapter
from src.mission_control.data_provider import DataProvider
from src.mission_control.session_logger import SessionLogger
from src.pods.base.gateway import PodGateway
from src.pods.base.namespace import PodNamespace
from src.pods.runtime.pod_runtime import PodRuntime
from src.core.config.universes import POD_UNIVERSES
from src.pods.templates.equities.researcher import EquitiesResearcher
from src.pods.templates.equities.signal_agent import EquitiesSignalAgent
from src.pods.templates.equities.pm_agent import EquitiesPMAgent
from src.pods.templates.equities.risk_agent import EquitiesRiskAgent
from src.pods.templates.equities.execution_trader import EquitiesExecutionTrader
from src.pods.templates.equities.ops_agent import EquitiesOpsAgent
from src.pods.templates.fx.researcher import FXResearcher
from src.pods.templates.fx.signal_agent import FXSignalAgent
from src.pods.templates.fx.pm_agent import FXPMAgent
from src.pods.templates.fx.risk_agent import FXRiskAgent
from src.pods.templates.fx.execution_trader import FXExecutionTrader
from src.pods.templates.fx.ops_agent import FXOpsAgent
from src.pods.templates.crypto.researcher import CryptoResearcher
from src.pods.templates.crypto.signal_agent import CryptoSignalAgent
from src.pods.templates.crypto.pm_agent import CryptoPMAgent
from src.pods.templates.crypto.risk_agent import CryptoRiskAgent
from src.pods.templates.crypto.execution_trader import CryptoExecutionTrader
from src.pods.templates.crypto.ops_agent import CryptoOpsAgent
from src.pods.templates.commodities.researcher import CommoditiesResearcher
from src.pods.templates.commodities.signal_agent import CommoditiesSignalAgent
from src.pods.templates.commodities.pm_agent import CommoditiesPMAgent
from src.pods.templates.commodities.risk_agent import CommoditiesRiskAgent
from src.pods.templates.commodities.execution_trader import CommoditiesExecutionTrader
from src.pods.templates.commodities.ops_agent import CommoditiesOpsAgent
from src.web.server import create_app

logger = logging.getLogger(__name__)

POD_IDS = ["equities", "fx", "crypto", "commodities"]

POD_AGENTS = {
    "equities": {
        "researcher": EquitiesResearcher,
        "signal": EquitiesSignalAgent,
        "pm": EquitiesPMAgent,
        "risk": EquitiesRiskAgent,
        "exec_trader": EquitiesExecutionTrader,
        "ops": EquitiesOpsAgent,
    },
    "fx": {
        "researcher": FXResearcher,
        "signal": FXSignalAgent,
        "pm": FXPMAgent,
        "risk": FXRiskAgent,
        "exec_trader": FXExecutionTrader,
        "ops": FXOpsAgent,
    },
    "crypto": {
        "researcher": CryptoResearcher,
        "signal": CryptoSignalAgent,
        "pm": CryptoPMAgent,
        "risk": CryptoRiskAgent,
        "exec_trader": CryptoExecutionTrader,
        "ops": CryptoOpsAgent,
    },
    "commodities": {
        "researcher": CommoditiesResearcher,
        "signal": CommoditiesSignalAgent,
        "pm": CommoditiesPMAgent,
        "risk": CommoditiesRiskAgent,
        "exec_trader": CommoditiesExecutionTrader,
        "ops": CommoditiesOpsAgent,
    },
}


class SessionManager:
    """Manage live paper trading session.

    Responsibilities:
    1. Initialize Alpaca adapter and 4 pods (equities, fx, crypto, commodities) with capital
    2. Fetch hourly bars per-pod universe from Alpaca
    3. Push bars to pod runtimes, run researcher + signal + PM agent cycles
    4. Run governance loops periodically (CEO, CIO, CRO)
    5. Emit pod summaries + research enrichment to EventBus
    6. Log all activity (trades, reasoning, conversations)
    """

    def __init__(
        self,
        alpaca_adapter: Optional[AlpacaAdapter] = None,
        event_bus: Optional[EventBus] = None,
        audit_log: Optional[AuditLog] = None,
        session_dir: Optional[str] = None,
        enable_web_server: bool = False,
        enable_news_adapters: bool = False,
    ):
        """Initialize session manager.

        Args:
            alpaca_adapter: AlpacaAdapter (default creates new instance)
            event_bus: EventBus (default creates new with audit_log)
            audit_log: AuditLog for EventBus (default in-memory)
            session_dir: Directory for logging (default auto-generated)
            enable_web_server: Enable FastAPI web server (default False)
            enable_news_adapters: Create FRED/GDELT/RSS adapters (default False)
        """
        self._enable_news_adapters = enable_news_adapters
        self._alpaca = alpaca_adapter or AlpacaAdapter()
        # Use file-based DuckDB if session_dir is provided for persistence across restarts
        if audit_log:
            self._audit_log = audit_log
        elif session_dir:
            db_path = str(Path(session_dir) / "audit.duckdb")
            self._audit_log = AuditLog(db_path=db_path)
        else:
            self._audit_log = AuditLog()
        self._event_bus = event_bus or EventBus(audit_log=self._audit_log)
        self._session_logger = SessionLogger(session_dir=session_dir)
        self._data_provider = DataProvider(bus=self._event_bus, audit_log=self._audit_log)

        self._pod_gateways: dict[str, PodGateway] = {}
        self._pod_runtimes: dict[str, PodRuntime] = {}
        self._pod_capital: dict[str, float] = {}
        self._governance: Optional[GovernanceOrchestrator] = None
        self._allocator: Optional[CapitalAllocator] = None

        # Governance state tracking
        self._latest_mandate: Optional[MandateUpdate] = None
        self._risk_halt: bool = False
        self._risk_halt_reason: Optional[str] = None
        self._governance_decisions: list = []

        # Web server state
        self._web_app = None
        self._web_server_task = None
        self._enable_web_server = enable_web_server

        self._session_active = False
        self._capital_per_pod = 0.0
        self._iteration = 0
        self._restartable = False
        self._stop_in_progress = False

        logger.info("[session_manager] Initialized with DataProvider and governance tracking")

    async def start_live_session(
        self,
        capital_per_pod: float = 100.0,
        initial_symbols: list[str] | None = None,
    ) -> None:
        """Start a live trading session.

        Args:
            capital_per_pod: Initial capital per pod (default $100)
            initial_symbols: Symbols to trade (default ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'AMZN'])
        """
        if initial_symbols is None:
            initial_symbols = ["SPY", "QQQ", "GLD", "BTC/USD", "UUP"]

        # Reinitialize resources for a fresh session (only if restarting after a stop)
        if self._iteration > 0 or self._restartable:
            try:
                self._session_logger.close()
            except Exception:
                pass
            self._session_logger = SessionLogger()
            self._data_provider = DataProvider(bus=self._event_bus, audit_log=self._audit_log)
            self._pod_runtimes = {}
            self._pod_gateways = {}
            self._pod_capital = {}
            self._iteration = 0

        self._start_time = datetime.now()
        self._session_start = datetime.now()
        self._capital_per_pod = capital_per_pod
        total_capital = capital_per_pod * len(POD_IDS)

        logger.info(
            "[session_manager] Starting live session: %d pods × $%.2f = $%.2f total",
            len(POD_IDS),
            capital_per_pod,
            total_capital,
        )

        try:
            # Verify Alpaca connectivity
            account = await self._alpaca.fetch_account()
            logger.info(
                "[session_manager] Alpaca account: equity=$%.2f, buying_power=$%.2f",
                account["equity"],
                account["buying_power"],
            )

            # Initialize DataProvider subscriptions
            await self._data_provider.subscribe_to_updates()
            logger.info("[session_manager] DataProvider subscriptions active")

            # Initialize CapitalAllocator (for CIO agent)
            self._allocator = CapitalAllocator(pod_ids=POD_IDS, bus=self._event_bus, audit_log=self._audit_log)
            logger.info("[session_manager] CapitalAllocator initialized with %d pods", len(POD_IDS))

            # Initialize pods with capital allocation
            for pod_id in POD_IDS:
                # Create PodConfig with sensible defaults for live trading
                pod_universe = POD_UNIVERSES.get(pod_id, initial_symbols)
                pod_config = PodConfig(
                    pod_id=pod_id,
                    name=f"{pod_id.capitalize()} Strategy",
                    strategy_family="multi-signal",
                    universe=pod_universe,
                    time_horizon=TimeHorizon.SWING,
                    risk_budget=RiskBudget(
                        target_vol=0.10,
                        max_leverage=2.0,
                        max_drawdown=0.15,
                        max_concentration=0.30,
                        max_sector_exposure=0.40,
                        liquidity_min_adv_pct=0.01,
                        var_limit_95=0.025,
                        es_limit_95=0.035,
                    ),
                    execution=ExecutionConfig(
                        style="neutral",
                        max_participation_rate=0.05,
                        allowed_venues=["NASDAQ", "NYSE"],
                        order_types=["market", "limit"],
                    ),
                    backtest=BacktestConfig(
                        start_date=datetime.now(timezone.utc).date(),
                        end_date=datetime.now(timezone.utc).date(),
                        min_history_days=252,
                        walk_forward_folds=1,
                        latency_ms=50,
                        tcm_bps=5.0,
                        slippage_model="sqrt_impact",
                    ),
                    pm_agent_type=AgentType.RULE_BASED,
                    enabled=True,
                )

                # Create PodNamespace (isolated state store)
                namespace = PodNamespace(pod_id)

                # Create PortfolioAccountant for this pod
                accountant = PortfolioAccountant(pod_id=pod_id, initial_nav=capital_per_pod)
                namespace.set("accountant", accountant)
                logger.info("[session_manager] Created PortfolioAccountant for pod %s: initial_nav=$%.2f", pod_id, capital_per_pod)

                # Create PodGateway (I/O boundary)
                gateway = PodGateway(pod_id, self._event_bus, pod_config)

                # Create PodRuntime
                runtime = PodRuntime(pod_id=pod_id, namespace=namespace, gateway=gateway, bus=self._event_bus)

                # Instantiate the 6 pod agents using pod-specific factories
                agent_classes = POD_AGENTS[pod_id]

                # Shared adapters (created once, reused across pods).
                # Only created when enable_news_adapters=True.
                if not hasattr(self, '_news_adapters_initialized'):
                    self._news_adapters_initialized = True
                    if self._enable_news_adapters:
                        self._fred_adapter: FredAdapter | None = FredAdapter()
                        self._rss_adapter: RssAdapter | None = RssAdapter()
                        self._gdelt_adapter: GdeltAdapter | None = GdeltAdapter()
                        self._x_adapter: XAdapter | None = XAdapter()
                        logger.info("[session] MVP3 news adapters enabled (incl. news RSS feeds)")
                        # Live price feeds: StockPrices.dev + CoinMarketCap + Alpha Vantage
                        self._price_service: PriceService | None = PriceService(
                            stockprices=StockPricesAdapter(),
                            coinmarketcap=CoinMarketCapAdapter(),
                            alphavantage=AlphaVantageAdapter(),
                        )
                    else:
                        self._fred_adapter = None
                        self._rss_adapter = None
                        self._gdelt_adapter = None
                        self._x_adapter = None
                        self._price_service = None

                # All pods get all available research adapters
                poly_adapter = PolymarketAdapter()
                market_tracker = MarketTracker(max_markets=30)
                researcher_kwargs = {
                    "agent_id": f"{pod_id}.researcher",
                    "pod_id": pod_id,
                    "namespace": namespace,
                    "bus": self._event_bus,
                    "polymarket_adapter": poly_adapter,
                    "market_tracker": market_tracker,
                }
                if self._fred_adapter:
                    researcher_kwargs["fred_adapter"] = self._fred_adapter
                if self._rss_adapter:
                    researcher_kwargs["rss_adapter"] = self._rss_adapter
                if self._x_adapter:
                    researcher_kwargs["x_adapter"] = self._x_adapter
                if self._price_service:
                    researcher_kwargs["price_service"] = self._price_service

                researcher = agent_classes["researcher"](**researcher_kwargs)
                signal = agent_classes["signal"](
                    agent_id=f"{pod_id}.signal", pod_id=pod_id, namespace=namespace, bus=self._event_bus
                )
                pm = agent_classes["pm"](
                    agent_id=f"{pod_id}.pm", pod_id=pod_id, namespace=namespace, bus=self._event_bus,
                    session_logger=self._session_logger
                )
                risk = agent_classes["risk"](
                    agent_id=f"{pod_id}.risk", pod_id=pod_id, namespace=namespace, bus=self._event_bus
                )
                # Pass Alpaca adapter and session_logger to exec_trader
                try:
                    exec_trader = agent_classes["exec_trader"](
                        agent_id=f"{pod_id}.exec_trader",
                        pod_id=pod_id,
                        namespace=namespace,
                        bus=self._event_bus,
                        alpaca_adapter=self._alpaca,
                        session_logger=self._session_logger
                    )
                except TypeError:
                    # Fallback for exec_traders that don't support both parameters
                    try:
                        exec_trader = agent_classes["exec_trader"](
                            agent_id=f"{pod_id}.exec_trader",
                            pod_id=pod_id,
                            namespace=namespace,
                            bus=self._event_bus,
                            alpaca_adapter=self._alpaca
                        )
                    except TypeError:
                        # Last resort fallback
                        exec_trader = agent_classes["exec_trader"](
                            agent_id=f"{pod_id}.exec_trader",
                            pod_id=pod_id,
                            namespace=namespace,
                            bus=self._event_bus
                        )
                ops = agent_classes["ops"](
                    agent_id=f"{pod_id}.ops", pod_id=pod_id, namespace=namespace, bus=self._event_bus
                )

                # Inject agents into runtime
                runtime.set_agents(researcher, signal, pm, risk, exec_trader, ops)

                # Store references
                self._pod_gateways[pod_id] = gateway
                self._pod_runtimes[pod_id] = runtime
                self._pod_capital[pod_id] = capital_per_pod

                # Subscribe to pod summary events for external monitoring
                await gateway.subscribe_market_data()

                logger.info(
                    "[session_manager] Pod %s initialized: capital=$%.2f, agents=6",
                    pod_id, capital_per_pod,
                )

            # Initialize governance orchestrator with CEO, CIO, CRO agents
            ceo = CEOAgent(bus=self._event_bus, session_logger=self._session_logger)
            cio = CIOAgent(bus=self._event_bus, allocator=self._allocator, session_logger=self._session_logger)
            cro = CROAgent(bus=self._event_bus)
            self._governance = GovernanceOrchestrator(
                ceo=ceo,
                cio=cio,
                cro=cro,
                session_logger=self._session_logger,
            )
            logger.info("[session_manager] GovernanceOrchestrator initialized: CEO, CIO, CRO")

            # Fetch initial market snapshot (small sample across all pods)
            sample_symbols = ["SPY", "QQQ", "GLD", "BTC/USD", "UUP"]
            try:
                bars = await self._alpaca.fetch_bars(sample_symbols)
                logger.info("[session_manager] Fetched initial bars for %d symbols", len(bars))
            except Exception as e:
                logger.warning("[session_manager] Initial bar fetch failed (non-fatal): %s", e)

            # Initialize web server if enabled
            if self._enable_web_server:
                await self._start_web_server(capital_per_pod)

            self._session_active = True
            logger.info("[session_manager] Session started: %d pods × $%.2f = $%.2f total capital",
                       len(POD_IDS), capital_per_pod, total_capital)

        except Exception as exc:
            logger.error("[session_manager] Failed to start session: %s", exc)
            raise

    async def _start_web_server(self, capital_per_pod: float) -> None:
        """Start FastAPI web server for dashboard.

        Args:
            capital_per_pod: Initial capital per pod
        """
        try:
            self._web_app = create_app(event_bus=self._event_bus, session_start_time=datetime.now(timezone.utc))

            # Initialize session state in app
            await self._web_app.state.update_session_state(
                iteration=0,
                capital_per_pod=capital_per_pod,
                pod_summaries={},
            )

            logger.info("[session_manager] FastAPI web server created (listening on localhost:8000)")
        except Exception as e:
            logger.error("[session_manager] Failed to start web server: %s", e)
            # Don't raise; allow session to continue without web server

    async def _update_web_state(self, pod_summaries: dict[str, PodSummary]) -> None:
        """Update web server state with latest pod summaries and governance info.

        Args:
            pod_summaries: Dictionary mapping pod_id to PodSummary
        """
        if not self._web_app:
            return

        try:
            # Convert PodSummary objects to dicts for web serialization
            pod_dicts = {}
            for pod_id, summary in pod_summaries.items():
                try:
                    pod_dicts[pod_id] = summary.model_dump(mode="json")
                except Exception:
                    pod_dicts[pod_id] = {}

                # Inject research data for all pods
                if pod_id in self._pod_runtimes:
                    ns = self._pod_runtimes[pod_id]._ns
                    pod_dicts[pod_id]["polymarket_signals"] = ns.get("polymarket_signals") or []
                    pod_dicts[pod_id]["polymarket_confidence"] = ns.get("polymarket_confidence") or 0.5
                    pod_dicts[pod_id]["macro_score"] = ns.get("macro_score")
                    pod_dicts[pod_id]["fred_snapshot"] = ns.get("fred_snapshot") or {}
                    pod_dicts[pod_id]["fred_score"] = ns.get("fred_score") or 0.0
                    pod_dicts[pod_id]["poly_sentiment"] = ns.get("poly_sentiment") or 0.0
                    pod_dicts[pod_id]["social_score"] = ns.get("social_score") or 0.0
                    all_feed = ns.get("x_feed") or []
                    pod_dicts[pod_id]["x_feed"] = all_feed[:100]
                    pod_dicts[pod_id]["x_tweet_count"] = len(all_feed)
                    pod_dicts[pod_id]["news_last_refresh"] = datetime.now(timezone.utc).isoformat()
                    pod_dicts[pod_id]["features"] = ns.get("features") or {}

            await self._web_app.state.update_session_state(
                iteration=self._iteration,
                capital_per_pod=self._capital_per_pod,
                pod_summaries=pod_dicts,
                risk_halt=self._risk_halt,
                risk_halt_reason=self._risk_halt_reason,
            )
        except Exception as e:
            logger.debug("[session_manager] Failed to update web state: %s", e)

    async def run_event_loop(
        self,
        interval_seconds: float = 3600.0,
        governance_freq: int = 4,
    ) -> None:
        """Run the main event loop.

        Fetches bars per-pod universe, runs agent cycles, governance, summaries.

        Args:
            interval_seconds: Sleep between iterations (default 3600 sec = 1 hour)
            governance_freq: Run governance every N iterations (default 4 = every 4 hours)
        """
        if not self._session_active:
            raise RuntimeError("Session not started; call start_live_session() first")

        logger.info(
            "[session_manager] Starting event loop: %.1f sec interval, governance every %d iter",
            interval_seconds,
            governance_freq,
        )

        try:
            while self._session_active:
                self._iteration += 1

                try:
                    # 1. Inject governance state to all pods (before bar processing)
                    for pod_id, runtime in self._pod_runtimes.items():
                        runtime.set_governance_state(
                            mandate=self._latest_mandate,
                            risk_halt=self._risk_halt,
                            risk_halt_reason=self._risk_halt_reason,
                        )

                    # 2. Run researcher cycles for all pods (so they can update universe)
                    for pod_id, runtime in self._pod_runtimes.items():
                        try:
                            researcher = runtime._researcher
                            if researcher:
                                res = await researcher.run_cycle({"bar": None})
                                logger.info(
                                    "[session_manager] [iter %d] %s researcher: %d signals",
                                    self._iteration, pod_id,
                                    len(res.get("poly_signals", [])),
                                )
                        except Exception as e:
                            logger.warning(
                                "[session_manager] [iter %d] %s researcher failed: %s",
                                self._iteration, pod_id, e,
                            )

                    # 3. Update gateway universes from namespace
                    for pod_id, gateway in self._pod_gateways.items():
                        runtime = self._pod_runtimes[pod_id]
                        gateway.set_universe(runtime._ns.get("universe") or POD_UNIVERSES.get(pod_id, []))

                    # 4. Per-pod: fetch bars for updated universes, push to gateway, mark-to-market
                    pod_latest_bars: dict[str, Bar | None] = {}
                    for pod_id, gateway in self._pod_gateways.items():
                        runtime = self._pod_runtimes[pod_id]
                        pod_symbols = runtime._ns.get("universe") or POD_UNIVERSES.get(pod_id, [])

                        try:
                            bars = await self._alpaca.fetch_bars(pod_symbols, timeframe="1Hour")
                            logger.info("[session_manager] [iter %d] Pod %s: fetched bars for %d symbols",
                                       self._iteration, pod_id, len(bars))
                        except Exception as e:
                            logger.error("[session_manager] [iter %d] Pod %s: bar fetch failed: %s",
                                        self._iteration, pod_id, e)
                            pod_latest_bars[pod_id] = None
                            continue

                        tick_prices = {}
                        latest_bar = None
                        bars_count = 0
                        for symbol in bars:
                            for bar in bars[symbol]:
                                try:
                                    await gateway.push_bar(bar)
                                    tick_prices[bar.symbol] = bar.close
                                    latest_bar = bar
                                    bars_count += 1
                                except Exception as e:
                                    logger.warning("[session_manager] push_bar failed for %s: %s", symbol, e)

                        if tick_prices:
                            accountant = runtime._ns.get("accountant")
                            if accountant:
                                accountant.mark_to_market(tick_prices)

                        pod_latest_bars[pod_id] = latest_bar
                        logger.info("[session_manager] [iter %d] Pod %s: ingested %d bars, mark-to-market done",
                                    self._iteration, pod_id, bars_count)

                    # 5. Run agent decision cycle ONCE per pod (signal → PM → risk → exec → ops)
                    for pod_id, runtime in self._pod_runtimes.items():
                        bar = pod_latest_bars.get(pod_id)
                        if bar is None:
                            continue
                        try:
                            await runtime.run_cycle(bar)
                            logger.info("[session_manager] [iter %d] Pod %s: agent cycle complete", self._iteration, pod_id)

                            # Publish PM decision activity for live intelligence feed
                            try:
                                ns = runtime._ns
                                last_decision = ns.get("last_pm_decision")
                                if last_decision:
                                    summary_text = last_decision.get("action_summary", "holding")
                                    detail_text = last_decision.get("reasoning", "")
                                else:
                                    summary_text = "holding"
                                    detail_text = ""
                                activity_msg = AgentMessage(
                                    timestamp=datetime.now(timezone.utc),
                                    sender=f"{pod_id}.pm",
                                    recipient="dashboard",
                                    topic="agent.activity",
                                    payload={
                                        "agent_id": f"{pod_id}_pm",
                                        "agent_role": "PM",
                                        "pod_id": pod_id,
                                        "action": "trade_decision",
                                        "summary": f"{pod_id.upper()} PM: {summary_text}"[:200],
                                        "detail": detail_text[:500],
                                    },
                                )
                                await self._event_bus.publish("agent.activity", activity_msg, publisher_id=f"{pod_id}.pm")
                            except Exception:
                                pass

                        except Exception as e:
                            logger.warning("[session_manager] [iter %d] Pod %s agent cycle failed: %s",
                                          self._iteration, pod_id, e)

                    # 4. Collect pod summaries for governance and emission
                    pod_summaries = await self._collect_pod_summaries()
                    logger.info("[session_manager] [iter %d] Collected %d pod summaries", self._iteration, len(pod_summaries))

                    # 5. Emit pod summaries to EventBus (for TUI and DataProvider)
                    for pod_id, gateway in self._pod_gateways.items():
                        summary = pod_summaries.get(pod_id)
                        if summary:
                            try:
                                await gateway.emit_summary(summary)
                                logger.debug(
                                    "[session_manager] [iter %d] Emitted summary for %s: NAV=%.2f",
                                    self._iteration, pod_id, summary.nav
                                )
                            except Exception as e:
                                logger.warning(
                                    "[session_manager] [iter %d] Failed to emit summary for %s: %s",
                                    self._iteration, pod_id, e
                                )

                    # 5.1 Broadcast research enrichment data for all pods
                    for pod_id, runtime in self._pod_runtimes.items():
                        try:
                            ns = runtime._ns
                            msg = AgentMessage(
                                timestamp=datetime.now(timezone.utc),
                                sender=f"pod.{pod_id}",
                                recipient="broadcast",
                                topic=f"pod.{pod_id}.gateway",
                                payload={
                                    "pod_id": pod_id,
                                    "polymarket_signals": ns.get("polymarket_signals") or [],
                                    "polymarket_confidence": ns.get("polymarket_confidence") or 0.5,
                                    "macro_score": ns.get("macro_score"),
                                    "fred_snapshot": ns.get("fred_snapshot") or {},
                                    "fred_score": ns.get("fred_score") or 0.0,
                                    "poly_sentiment": ns.get("poly_sentiment") or 0.0,
                                    "social_score": ns.get("social_score") or 0.0,
                                    "x_feed": (ns.get("x_feed") or [])[:100],
                                    "x_tweet_count": len(ns.get("x_feed") or []),
                                    "news_last_refresh": datetime.now(timezone.utc).isoformat(),
                                },
                            )
                            await self._event_bus.publish(
                                f"pod.{pod_id}.gateway", msg, publisher_id=f"pod.{pod_id}"
                            )
                        except Exception as e:
                            logger.debug("[session_manager] %s enrichment broadcast failed: %s", pod_id, e)

                    # 5.5. Update web server state with latest summaries
                    if self._enable_web_server:
                        await self._update_web_state(pod_summaries)

                    # 6. Every N iterations: run governance cycle
                    if self._iteration > 0 and self._iteration % governance_freq == 0:
                        try:
                            logger.info("[session_manager] [iter %d] Running governance cycle", self._iteration)
                            governance_result = await self._governance.run_full_cycle(pod_summaries)

                            # Extract results
                            breached_pods = governance_result.get("breached_pods", [])
                            mandate = governance_result.get("mandate")

                            # Store latest mandate for execution enforcement
                            if mandate:
                                self._latest_mandate = mandate
                                logger.info(
                                    "[session_manager] [iter %d] Mandate updated: allocations=%s, firm_nav=%.2f",
                                    self._iteration,
                                    mandate.pod_allocations,
                                    mandate.firm_nav,
                                )

                            # Check for CRO halt
                            if governance_result.get("cro_halt"):
                                self._risk_halt = True
                                self._risk_halt_reason = governance_result.get("cro_halt_reason", "Unknown")
                                logger.error(
                                    "[session_manager] [iter %d] RISK HALT ACTIVE: %s",
                                    self._iteration, self._risk_halt_reason
                                )
                            else:
                                self._risk_halt = False
                                self._risk_halt_reason = None

                            # Log governance cycle
                            self._session_logger.log_reasoning(
                                "governance",
                                "cycle",
                                f"Iteration {self._iteration}: Breached={breached_pods}, "
                                f"Loop6_Consensus={governance_result.get('loop6_consensus', False)}, "
                                f"Loop7_Consensus={governance_result.get('loop7_consensus', False)}, "
                                f"RiskHalt={self._risk_halt}",
                                metadata={
                                    "iteration": self._iteration,
                                    "breached_pods": breached_pods,
                                    "loop6_consensus": governance_result.get("loop6_consensus", False),
                                    "loop7_consensus": governance_result.get("loop7_consensus", False),
                                    "mandate_authorized_by": mandate.authorized_by if mandate else None,
                                    "risk_halt": self._risk_halt,
                                    "risk_halt_reason": self._risk_halt_reason,
                                }
                            )

                            if breached_pods:
                                logger.warning(
                                    "[session_manager] [iter %d] Risk breach detected in pods: %s",
                                    self._iteration, breached_pods
                                )

                            # Publish governance summary activity
                            try:
                                gov_summary = (
                                    f"Governance cycle complete. "
                                    f"Breached: {breached_pods or 'none'}. "
                                    f"Risk halt: {self._risk_halt}."
                                )
                                gov_activity = AgentMessage(
                                    timestamp=datetime.now(timezone.utc),
                                    sender="governance",
                                    recipient="dashboard",
                                    topic="agent.activity",
                                    payload={
                                        "agent_id": "governance",
                                        "agent_role": "CRO",
                                        "pod_id": "firm",
                                        "action": "governance_cycle",
                                        "summary": gov_summary[:200],
                                        "detail": "",
                                    },
                                )
                                await self._event_bus.publish("agent.activity", gov_activity, publisher_id="governance")
                            except Exception:
                                pass

                        except Exception as e:
                            logger.error(
                                "[session_manager] [iter %d] Governance cycle failed: %s",
                                self._iteration, e, exc_info=True
                            )

                    # 7. Periodic account logging + position reconciliation
                    if self._iteration % 10 == 0:
                        try:
                            account = await self._alpaca.fetch_account()
                            logger.info(
                                "[session_manager] [iter %d] Account: equity=$%.2f, positions=%d",
                                self._iteration,
                                account["equity"],
                                account["position_count"],
                            )
                        except Exception as e:
                            logger.warning("[session_manager] [iter %d] Failed to fetch account: %s", self._iteration, e)

                        await self._reconcile_positions()

                    # 8. Sleep
                    await asyncio.sleep(interval_seconds)

                except asyncio.CancelledError:
                    logger.info("[session_manager] Event loop cancelled")
                    break
                except Exception as exc:
                    logger.error("[session_manager] [iter %d] Event loop error: %s", self._iteration, exc)
                    # Continue running; don't exit on transient errors
                    await asyncio.sleep(interval_seconds)

        finally:
            await self.stop_session()

    async def publish_pod_summary(self, pod_id: str, summary: dict) -> None:
        """Publish pod summary to EventBus for TUI consumption.

        Args:
            pod_id: ID of the pod (e.g., 'equities', 'fx')
            summary: Pod summary dict with risk_metrics, positions, etc.
        """
        msg = AgentMessage(
            timestamp=datetime.now(timezone.utc),
            sender=f"pod.{pod_id}.gateway",
            recipient="*",
            topic=f"pod.{pod_id}.gateway",
            payload=summary,
        )
        await self._event_bus.publish(f"pod.{pod_id}.gateway", msg, publisher_id=f"pod.{pod_id}")
        logger.debug("[session_manager] Published pod %s summary", pod_id)

    async def _collect_pod_summaries(self) -> dict[str, PodSummary]:
        """Collect current summary from each pod runtime.

        Returns:
            Dictionary mapping pod_id to PodSummary.
        """
        summaries: dict[str, PodSummary] = {}
        for pod_id, runtime in self._pod_runtimes.items():
            try:
                summary = await runtime.get_summary()
                summaries[pod_id] = summary
                logger.debug("[session_manager] Collected summary for pod %s", pod_id)
            except Exception as exc:
                logger.warning("[session_manager] Error collecting summary for pod %s: %s", pod_id, exc)
                # Continue with next pod even if one fails
        return summaries

    async def _reconcile_positions(self) -> None:
        """Compare Alpaca positions against per-pod accountant positions.

        Alpaca tracks aggregate positions (not per-pod), so this is
        best-effort.  Discrepancies are logged as warnings, not auto-corrected.
        Also cancels stale open orders (pending > 60s).
        """
        try:
            alpaca_positions = await self._alpaca.get_open_positions()
            for pod_id, runtime in self._pod_runtimes.items():
                accountant = runtime._ns.get("accountant")
                if not accountant:
                    continue
                for symbol, snapshot in accountant.current_positions.items():
                    alpaca_pos = alpaca_positions.get(symbol)
                    if alpaca_pos is None:
                        logger.warning(
                            "[reconcile] %s has %s in accountant but NOT in Alpaca",
                            pod_id, symbol,
                        )
                    elif abs(alpaca_pos["qty"] - snapshot.qty) > 0.01:
                        logger.warning(
                            "[reconcile] %s %s qty mismatch: accountant=%.2f, alpaca=%.2f",
                            pod_id, symbol, snapshot.qty, alpaca_pos["qty"],
                        )
        except Exception as e:
            logger.warning("[reconcile] Position reconciliation failed: %s", e)

        try:
            from datetime import datetime, timezone
            open_orders = await self._alpaca.get_all_open_orders()
            now = datetime.now(timezone.utc)
            for o in open_orders:
                submitted = o.get("submitted_at")
                if submitted and hasattr(submitted, "timestamp"):
                    age_s = (now - submitted.replace(tzinfo=timezone.utc)).total_seconds()
                    if age_s > 60:
                        logger.warning(
                            "[reconcile] Cancelling stale order %s (%s, %.0fs old)",
                            o["order_id"], o["symbol"], age_s,
                        )
                        await self._alpaca.cancel_order(o["order_id"])
        except Exception as e:
            logger.debug("[reconcile] Stale order cleanup skipped: %s", e)

    async def stop_session(self) -> dict:
        """Stop event loop and gracefully shut down all pods.

        Returns:
            Dictionary with session summary: uptime_seconds, iterations, pods_closed, final_capital.
        """
        if self._stop_in_progress:
            return {"already_stopped": True}
        self._stop_in_progress = True
        logger.info("[session_manager] Stopping live session")
        self._session_active = False

        # Give current iteration time to complete
        await asyncio.sleep(0.5)

        # Gracefully shut down all pod runtimes
        closed_count = 0
        for pod_id, runtime in self._pod_runtimes.items():
            try:
                if hasattr(runtime, 'stop'):
                    await runtime.stop()
                logger.info("[session_manager] Stopped pod runtime: %s", pod_id)
                closed_count += 1
            except Exception as exc:
                logger.warning("[session_manager] Error stopping pod %s: %s", pod_id, exc)

        # Stop web server if running
        if self._web_server_task:
            try:
                self._web_server_task.cancel()
                await asyncio.sleep(0.1)
                logger.info("[session_manager] Web server task cancelled")
            except Exception as e:
                logger.warning("[session_manager] Error stopping web server: %s", e)

        # Close session logger
        try:
            self._session_logger.close()
            logger.info("[session_manager] Session logs saved to: %s", self._session_logger.session_dir)
        except Exception as e:
            logger.error("[session_manager] Error closing session logger: %s", e)

        # Close DuckDB audit log to release file lock (critical on Windows)
        # Skip if session may be restarted via dashboard
        if not self._restartable:
            try:
                self._audit_log.close()
                logger.info("[session_manager] Audit log closed")
            except Exception as e:
                logger.warning("[session_manager] Error closing audit log: %s", e)

        # Generate daily report
        try:
            from src.reports.daily_report import DailyReportGenerator
            from src.reports.email_sender import EmailSender

            pods_data = {}
            for pid, runtime in self._pod_runtimes.items():
                try:
                    summary = await runtime.get_summary()
                    pods_data[pid] = summary.model_dump(mode="json") if hasattr(summary, "model_dump") else {}
                except Exception:
                    pods_data[pid] = {}

            report_html = DailyReportGenerator().generate(
                session_dir=self._session_logger.session_dir if self._session_logger else "",
                session_start=getattr(self, "_session_start", None),
                session_end=datetime.now(),
                pods_data=pods_data,
                trades=self._session_logger._fill_log if self._session_logger else [],
                governance=getattr(self, "_governance_decisions", []),
                firm_nav=sum(p.get("risk_metrics", {}).get("nav", 0) for p in pods_data.values()),
                initial_capital=sum(p.get("risk_metrics", {}).get("starting_capital", 0) for p in pods_data.values()),
            )

            session_dir = self._session_logger.session_dir if self._session_logger else None
            if session_dir:
                report_path = os.path.join(
                    session_dir, f"daily_report_{datetime.now().strftime('%Y%m%d')}.html"
                )
                with open(report_path, "w", encoding="utf-8") as f:
                    f.write(report_html)
                logger.info("[session_manager] Daily report saved to %s", report_path)

            sender = EmailSender()
            if sender.is_configured:
                date_str = datetime.now().strftime("%Y-%m-%d")
                sender.send(f"Agentic HF Daily Report — {date_str}", report_html)
        except Exception as e:
            logger.warning("[session_manager] Daily report generation failed: %s", e)

        # Calculate uptime
        uptime_seconds = (datetime.now() - self._start_time).total_seconds() if hasattr(self, '_start_time') else 0

        self._stop_in_progress = False

        # Return session summary
        return {
            "uptime_seconds": uptime_seconds,
            "iterations": self._iteration,
            "pods_closed": closed_count,
            "final_capital": self._capital_per_pod * len(self._pod_runtimes),
        }

    @property
    def session_active(self) -> bool:
        """Whether the trading session is currently running."""
        return self._session_active

    @property
    def iteration(self) -> int:
        """Current event loop iteration count."""
        return self._iteration

    @property
    def event_bus(self) -> EventBus:
        """Access the EventBus instance for external consumers (e.g., TUI)."""
        return self._event_bus

    @property
    def data_provider(self) -> DataProvider:
        """Access the DataProvider for TUI injection."""
        return self._data_provider

    @property
    def latest_mandate(self) -> Optional[MandateUpdate]:
        """Get the latest mandate from governance cycle."""
        return self._latest_mandate

    @property
    def risk_halt(self) -> bool:
        """Check if execution is halted due to risk constraints."""
        return self._risk_halt

    @property
    def risk_halt_reason(self) -> Optional[str]:
        """Get the reason for risk halt."""
        return self._risk_halt_reason

    def log_trade(
        self,
        pod_id: str,
        order_id: str,
        symbol: str,
        side: str,
        qty: float,
        filled_price: float | None = None,
    ) -> None:
        """Log a trade execution.

        Args:
            pod_id: Pod that placed order
            order_id: Alpaca order ID
            symbol: Ticker
            side: 'buy' or 'sell'
            qty: Quantity
            filled_price: Fill price (None if not filled yet)
        """
        self._session_logger.log_trade(
            pod_id=pod_id,
            order_id=order_id,
            symbol=symbol,
            side=side,
            qty=qty,
            filled_price=filled_price,
            status="submitted",
        )

    def get_session_dir(self) -> str:
        """Get the session log directory."""
        return self._session_logger.session_dir

    # Context manager support
    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.stop_session()
