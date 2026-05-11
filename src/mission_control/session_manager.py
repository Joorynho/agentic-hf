"""Live paper trading session manager — orchestrate pods, governance, and logging."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load .env file at module import time
_env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(str(_env_path))

from src.agents.ceo.ceo_agent import CEOAgent
from src.agents.cio.cio_agent import CIOAgent
from src.agents.cio.pod_scorer import score_pod
from src.agents.governance.governance_orchestrator import GovernanceOrchestrator
from src.agents.governance.position_reviewer import PositionReviewer
from src.agents.risk.cro_agent import CROAgent
from src.backtest.accounting.capital_allocator import CapitalAllocator
from src.backtest.accounting.portfolio import PortfolioAccountant
from src.core.position_monitor import PositionMonitor
from src.core.position_aging import check_aging
from src.core.concentration import aggregate_exposure
from src.core.loss_review import build_loss_review, format_loss_review_for_prompt
from src.core.bus.audit_log import AuditLog
from src.core.bus.event_bus import EventBus
from src.core.state.nav_store import NavStore
from src.data.adapters.fred_adapter import FredAdapter
from src.data.adapters.gdelt_adapter import GdeltAdapter
from src.data.adapters.market_tracker import MarketTracker
from src.data.adapters.polymarket_adapter import PolymarketAdapter
from src.data.adapters.rss_adapter import RssAdapter
from src.data.adapters.x_adapter import XAdapter
from src.data.services.research_ingestion import ResearchIngestionService
from src.data.adapters.price_service import (
    PriceService,
    canonical_crypto_symbol,
    is_crypto_symbol,
    symbol_aliases,
)
from src.data.adapters.stockprices_adapter import StockPricesAdapter
from src.data.adapters.coinmarketcap_adapter import CoinMarketCapAdapter
from src.data.adapters.alphavantage_adapter import AlphaVantageAdapter
from src.data.adapters.benchmark import BenchmarkAdapter
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
        self._restored_memory: dict | None = None

        # Web server state
        self._web_app = None
        self._web_server_task = None
        self._enable_web_server = enable_web_server
        self._external_web_app = False

        self._session_active = False
        self._capital_per_pod = 0.0
        self._iteration = 0
        self._restartable = False
        self._stop_in_progress = False

        # Position review state
        self._position_reviewer: PositionReviewer | None = None
        self._last_review_date: str | None = None
        self._reports_dir = str(Path(__file__).parent.parent.parent / "reports")

        # Intraday position monitor
        self._position_monitor = PositionMonitor()

        # Source attribution: tracks per-source (FRED/Poly/News) win rates to
        # dynamically adjust macro score weights over time.
        from src.core.source_attribution import SourceAttributor
        self._source_attributors: dict[str, SourceAttributor] = {}

        # NAV history (SQLite), benchmarks, firm-level P&L continuity
        self._nav_store: NavStore | None = None
        self._benchmark_adapter: BenchmarkAdapter | None = None
        self._benchmark_returns: dict = {}
        self._firm_peak_nav: float = 0.0
        self._firm_inception_pnl: float = 0.0
        self._last_total_realized_snapshot: float = 0.0
        self._last_drawdown_tier: str = "none"
        self._cro_agent = None
        self._last_broker_reconciliation: dict | None = None
        self._broker_reconciliation_timeout_s: float = 2.5
        self._last_position_price_refresh_at: float = 0.0
        self._position_price_refresh_min_interval_s: float = 20.0
        self._position_price_refresh_lock = asyncio.Lock()
        self._loss_reviews: dict[str, dict] = {}
        self._loss_review_history: list[dict] = []
        self._loss_review_last_signature: dict[str, str] = {}

        logger.info("[session_manager] Initialized with DataProvider and governance tracking")

    def set_web_app(self, app) -> None:
        """Inject an externally-created FastAPI app so _update_web_state can update it."""
        self._web_app = app
        self._external_web_app = True

    async def start_live_session(
        self,
        capital_per_pod: float = 1000.0,
        initial_symbols: list[str] | None = None,
    ) -> None:
        """Start a live trading session.

        Args:
            capital_per_pod: Initial capital per pod (default $1000)
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
            self._loss_reviews = {}
            self._loss_review_history = []
            self._loss_review_last_signature = {}

        self._start_time = datetime.now()
        self._session_start = datetime.now()
        self._MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        if self._nav_store:
            try:
                self._nav_store.close()
            except Exception:
                pass
            self._nav_store = None
        self._nav_store = NavStore(str(self._MEMORY_DIR / "state.db"))
        try:
            repaired = self._nav_store.repair_collapsed_snapshots()
            if repaired:
                logger.info("[session_manager] Repaired %d collapsed NAV snapshot(s)", repaired)
        except Exception as e:
            logger.debug("[session_manager] NAV history repair skipped: %s", e)
        self._benchmark_adapter = BenchmarkAdapter()
        self._benchmark_returns = {}
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

                # Expose audit_log to pod namespace so PM agents can persist decisions
                namespace.set("audit_log", self._audit_log)

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

            # Initialize one SourceAttributor per pod (reset on session restart)
            from src.core.source_attribution import SourceAttributor
            self._source_attributors = {pod_id: SourceAttributor() for pod_id in self._pod_runtimes}
            logger.info("[session_manager] SourceAttributors initialized for %d pods", len(self._source_attributors))

            # Create shared research ingestion service (fetches FRED/Polymarket/RSS/X once per 5 min)
            self._research_ingestion = ResearchIngestionService(
                fred_adapter=getattr(self, "_fred_adapter", None),
                polymarket_adapter=PolymarketAdapter(),
                rss_adapter=getattr(self, "_rss_adapter", None),
                x_adapter=getattr(self, "_x_adapter", None),
                interval_seconds=300,
                feed_store_path=str(self._MEMORY_DIR / "research_feed.duckdb"),
            )
            logger.info("[session_manager] ResearchIngestionService created")

            # Initialize governance orchestrator with CEO, CIO, CRO agents
            ceo = CEOAgent(bus=self._event_bus, session_logger=self._session_logger)
            cio = CIOAgent(bus=self._event_bus, allocator=self._allocator, session_logger=self._session_logger)
            cro = CROAgent(bus=self._event_bus)
            self._cro_agent = cro
            self._cio_agent = cio
            self._governance = GovernanceOrchestrator(
                ceo=ceo,
                cio=cio,
                cro=cro,
                session_logger=self._session_logger,
            )
            logger.info("[session_manager] GovernanceOrchestrator initialized: CEO, CIO, CRO")

            # Initialize PositionReviewer for daily position reviews
            self._position_reviewer = PositionReviewer(
                event_bus=self._event_bus,
                session_logger=self._session_logger,
            )
            os.makedirs(self._reports_dir, exist_ok=True)
            logger.info("[session_manager] PositionReviewer initialized, reports dir: %s", self._reports_dir)

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

            # Hydrate accountants from Alpaca (source of truth for live positions)
            await self._hydrate_from_alpaca()

            # Restore trade history + governance from previous session
            self._restored_memory = self._load_memory()
            if self._restored_memory:
                # Restore trade outcome trackers and signal scorers
                from src.core.trade_outcomes import TradeOutcomeTracker
                from src.core.signal_scorer import SignalScorer
                saved_outcomes = self._restored_memory.get("trade_outcomes", {})
                for pod_id, outcome_state in saved_outcomes.items():
                    rt = self._pod_runtimes.get(pod_id)
                    if rt:
                        rt._outcome_tracker = TradeOutcomeTracker.load_from_state(outcome_state)
                        logger.info("[session_manager] Restored %d trade outcomes for %s",
                                    rt._outcome_tracker.total_trades, pod_id)
                saved_scores = self._restored_memory.get("signal_scores", {})
                for pod_id, score_state in saved_scores.items():
                    rt = self._pod_runtimes.get(pod_id)
                    if rt:
                        rt._signal_scorer = SignalScorer.load_from_state(score_state)
                        logger.info("[session_manager] Restored signal scorer for %s", pod_id)

                # Backfill entry metadata for hydrated positions from memory trades
                self._backfill_entry_metadata_from_memory(self._restored_memory)

                saved_pods = self._restored_memory.get("pods", {}) or {}
                for pod_id, runtime in self._pod_runtimes.items():
                    acct = runtime._ns.get("accountant")
                    if acct and pod_id in saved_pods:
                        acct.load_entry_state(saved_pods[pod_id])

                firm_prev = self._restored_memory.get("firm", {}) or {}
                self._firm_inception_pnl = float(firm_prev.get("inception_pnl", 0.0) or 0.0)
                self._firm_peak_nav = float(firm_prev.get("peak_nav", 0.0) or 0.0)
                self._last_total_realized_snapshot = sum(
                    float(saved_pods.get(pid, {}).get("realized_pnl", 0) or 0)
                    for pid in POD_IDS
                )

                # Restore governance decisions so they persist across restarts
                restored_gov = self._restored_memory.get("governance", [])
                if restored_gov:
                    self._governance_decisions = list(restored_gov)
                    logger.info("[session_manager] Restored %d governance decisions from memory", len(restored_gov))

                restored_loss = self._restored_memory.get("loss_reviews", {}) or {}
                if isinstance(restored_loss, dict):
                    self._loss_reviews = dict(restored_loss.get("active", {}) or {})
                    self._loss_review_history = list(restored_loss.get("history", []) or [])[-100:]
                    for _pid, _review in self._loss_reviews.items():
                        rt = self._pod_runtimes.get(_pid)
                        if rt and isinstance(_review, dict):
                            rt._ns.set("loss_review", _review)
                            rt._ns.set("loss_review_restriction", _review.get("restriction", {}))
                    if self._loss_reviews or self._loss_review_history:
                        logger.info(
                            "[session_manager] Restored loss reviews: %d active, %d historical",
                            len(self._loss_reviews),
                            len(self._loss_review_history),
                        )

                # Restore research enrichment data to pod namespaces
                restored_enrichment = self._restored_memory.get("enrichment", {})
                for pod_id, enrich in restored_enrichment.items():
                    rt = self._pod_runtimes.get(pod_id)
                    if rt:
                        ns = rt._ns
                        for key in ("fred_snapshot", "fred_score", "polymarket_signals",
                                    "polymarket_confidence", "macro_score", "poly_sentiment",
                                    "social_score", "x_feed"):
                            if key in enrich and not ns.get(key):
                                ns.set(key, enrich[key])
                        logger.info("[session_manager] Restored enrichment for %s", pod_id)

                # Restore discovered universe into pod namespaces
                disc_univ = self._restored_memory.get("discovered_universe", {})
                for pod_id, pod_disc in disc_univ.items():
                    rt = self._pod_runtimes.get(pod_id)
                    if rt and pod_disc.get("tickers"):
                        rt._ns.set("discovered_tickers", pod_disc["tickers"])
                        logger.info("[session_manager] Restored %d discovered tickers for %s",
                                    len(pod_disc["tickers"]), pod_id)

                if self._web_app:
                    lsnr = getattr(self._web_app.state, "listener", None)
                    if lsnr:
                        lsnr.inject_restored_memory(self._restored_memory)

            # Emit initial pod summaries via gateways so dashboard receives live broadcasts
            # and the snapshot store is populated before any client connects
            if self._web_app:
                try:
                    initial_summaries = {}
                    for pod_id, rt in self._pod_runtimes.items():
                        summary = await rt.get_summary()
                        initial_summaries[pod_id] = summary
                    await self._update_web_state(initial_summaries)
                    # Also broadcast via gateways so already-connected clients get the update
                    for pod_id, summary in initial_summaries.items():
                        gateway = self._pod_gateways.get(pod_id)
                        if gateway:
                            await gateway.emit_summary(summary)
                    logger.info("[session_manager] Broadcast initial pod summaries (%d pods)", len(initial_summaries))
                except Exception as e:
                    logger.warning("[session_manager] Failed to send initial web state: %s", e)

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

    def _build_pod_intelligence_briefs(self, pod_summaries: dict[str, PodSummary]) -> dict[str, dict]:
        """Build intelligence briefs from each pod's namespace for CIO context."""
        briefs: dict[str, dict] = {}
        for pod_id, runtime in self._pod_runtimes.items():
            brief: dict = {}
            ns = runtime._ns if hasattr(runtime, "_ns") else None
            if ns:
                features = ns.get("features") or {}
                brief["macro_regime"] = features.get("macro_outlook", "unknown")
                poly = features.get("polymarket_predictions", [])
                brief["top_signals"] = [
                    f"{p.get('question','?')} → {p.get('probability',0)*100:.0f}%"
                    for p in (poly[:5] if poly else [])
                ]
                fred = features.get("fred_indicators", {})
                if fred:
                    brief["fred_highlights"] = ", ".join(
                        f"{k}={v}" for k, v in list(fred.items())[:6] if v is not None
                    )

            summary = pod_summaries.get(pod_id)
            if summary and summary.positions:
                brief["key_positions"] = [
                    f"{p.symbol}: qty={p.qty:.2f}, notional=${p.notional:,.0f}, pnl=${p.unrealized_pnl:+,.2f}"
                    for p in summary.positions[:5]
                ]

            # Performance attribution from trade outcome tracker
            tracker = getattr(runtime, "_outcome_tracker", None)
            if tracker and tracker.total_trades > 0:
                brief["performance"] = {
                    "total_trades": tracker.total_trades,
                    "win_rate": f"{tracker.win_rate:.0%}",
                    "total_realized_pnl": f"${tracker.total_pnl:.2f}",
                    "avg_pnl_per_trade": f"${tracker.avg_pnl:.2f}",
                }

            # Performance analytics (Sharpe, vol, drawdown)
            if ns:
                perf_summary = ns.get("performance_summary")
                if perf_summary:
                    brief["performance_metrics"] = perf_summary

            # Cross-pod conflict check (injected per pod)
            if hasattr(self._governance, "check_cross_pod_conflicts"):
                conflicts = self._governance.check_cross_pod_conflicts(pod_summaries)
                if conflicts:
                    brief["cross_pod_conflicts"] = conflicts

            briefs[pod_id] = brief
        return briefs

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
                    pod_dicts[pod_id]["loss_review"] = ns.get("loss_review") or {}
                    pod_dicts[pod_id]["loss_review_restriction"] = ns.get("loss_review_restriction") or {}

            await self._web_app.state.update_session_state(
                iteration=self._iteration,
                capital_per_pod=self._capital_per_pod,
                pod_summaries=pod_dicts,
                risk_halt=self._risk_halt,
                risk_halt_reason=self._risk_halt_reason,
                firm_inception_pnl=self._firm_inception_pnl,
                firm_peak_nav=self._firm_peak_nav,
                benchmark_returns=self._benchmark_returns,
                drawdown_tier=self._last_drawdown_tier,
                loss_reviews=self.get_loss_review_report(),
            )
        except Exception as e:
            logger.debug("[session_manager] Failed to update web state: %s", e)

    def _today_baseline_nav(self, pod_id: str, fallback: float) -> float:
        """First persisted NAV for this pod today, falling back to starting capital."""
        fallback = float(fallback or 0.0)
        if not self._nav_store:
            return fallback
        try:
            today = datetime.now(timezone.utc).date()
            rows = self._nav_store.read_history(pod_id=pod_id, limit=2000)
            for row in rows:
                ts = str(row.get("ts") or "")
                if not ts:
                    continue
                try:
                    parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    if parsed.astimezone(timezone.utc).date() == today:
                        nav = float(row.get("nav") or 0.0)
                        if nav > 0:
                            return nav
                except Exception:
                    continue
        except Exception as e:
            logger.debug("[session_manager] loss review baseline failed for %s: %s", pod_id, e)
        return fallback

    async def _refresh_loss_reviews(self) -> None:
        """Evaluate pod-level loss reviews and push restrictions into runtimes."""
        now = datetime.now(timezone.utc)
        for pod_id, runtime in self._pod_runtimes.items():
            acct = runtime._ns.get("accountant")
            if not acct:
                continue
            try:
                nav = float(acct.nav)
                starting = float(getattr(acct, "starting_capital", self._capital_per_pod) or self._capital_per_pod or nav)
                baseline = self._today_baseline_nav(pod_id, starting)
                review = build_loss_review(
                    pod_id=pod_id,
                    nav=nav,
                    starting_capital=starting,
                    positions=acct.current_positions.values(),
                    closed_trades=acct.closed_trades,
                    baseline_nav=baseline,
                    now=now,
                    iteration=self._iteration,
                )

                previous = self._loss_reviews.get(pod_id, {})
                if previous.get("created_at") and previous.get("status") == review.get("status"):
                    review["created_at"] = previous.get("created_at")

                self._loss_reviews[pod_id] = review
                runtime._ns.set("loss_review", review)
                runtime._ns.set("loss_review_restriction", review.get("restriction", {}))
                runtime._ns.set("loss_review_text", format_loss_review_for_prompt(review))

                signature = f"{review.get('status')}|{review.get('trigger_reason')}"
                changed = self._loss_review_last_signature.get(pod_id) != signature
                if changed:
                    self._loss_review_last_signature[pod_id] = signature

                should_emit = review.get("triggered") and (changed or self._iteration % 5 == 0)
                if should_emit:
                    entry = dict(review)
                    self._loss_review_history.insert(0, entry)
                    self._loss_review_history = self._loss_review_history[:100]
                    try:
                        await self._event_bus.publish(
                            "risk.alert",
                            AgentMessage(
                                timestamp=now,
                                sender="cro",
                                recipient="dashboard",
                                topic="risk.alert",
                                payload={
                                    "pod_id": pod_id,
                                    "message": f"{pod_id.upper()} loss review: {review.get('trigger_reason')}",
                                    "severity": review.get("severity", "warning"),
                                    "action": "loss_review",
                                    "loss_review": review,
                                },
                            ),
                            publisher_id="cro",
                        )
                        await self._event_bus.publish(
                            "agent.activity",
                            AgentMessage(
                                timestamp=now,
                                sender="cro",
                                recipient="dashboard",
                                topic="agent.activity",
                                payload={
                                    "agent_id": "cro",
                                    "agent_role": "CRO",
                                    "pod_id": pod_id,
                                    "action": "loss_review",
                                    "summary": f"{pod_id.upper()} loss review: {review.get('status', 'watch').upper()}",
                                    "detail": review.get("pm_defense_prompt", ""),
                                },
                            ),
                            publisher_id="cro",
                        )
                    except Exception as e:
                        logger.debug("[session_manager] loss review alert failed for %s: %s", pod_id, e)
            except Exception as e:
                logger.debug("[session_manager] loss review failed for %s: %s", pod_id, e)

    def get_loss_review_report(self) -> dict:
        """Return active and historical pod loss reviews for the dashboard."""
        active = dict(self._loss_reviews)
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "active": active,
            "history": list(self._loss_review_history[:100]),
            "count": len(active),
            "triggered_count": sum(1 for r in active.values() if r.get("triggered")),
        }

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

        # Start background price ticker (updates prices between iterations)
        ticker_task = asyncio.create_task(self._run_price_ticker())

        # Start shared research ingestion service (FRED/Poly/RSS/X fetched once per 5 min)
        if hasattr(self, "_research_ingestion") and self._research_ingestion:
            await self._research_ingestion.start()

        try:
            while self._session_active:
                self._iteration += 1
                if self._web_app:
                    try:
                        self._web_app.state.iteration = self._iteration
                        listener = getattr(self._web_app.state, "listener", None)
                        if listener is not None:
                            await listener.manager.broadcast({
                                "type": "session_status",
                                "data": {"active": True, "iteration": self._iteration},
                            })
                    except Exception:
                        pass

                try:
                    # 1. Inject governance state to all pods (before bar processing)
                    for pod_id, runtime in self._pod_runtimes.items():
                        runtime.set_governance_state(
                            mandate=self._latest_mandate,
                            risk_halt=self._risk_halt,
                            risk_halt_reason=self._risk_halt_reason,
                        )

                    # 1.5 Daily position review (fires once per calendar day)
                    await self._maybe_run_position_review()

                    # 2. Inject shared research data into each pod namespace before researchers run
                    if hasattr(self, "_research_ingestion") and self._research_ingestion and self._research_ingestion.last_fetch_time:
                        _shared = self._research_ingestion.get_shared_data()
                        for _pid, _rt in self._pod_runtimes.items():
                            _ns = _rt._ns
                            if _shared.get("fred_snapshot"):
                                _ns.set("shared_fred_snapshot", _shared["fred_snapshot"])
                            if _shared.get("poly_signals") is not None:
                                _ns.set("shared_poly_signals", _shared["poly_signals"])
                            if _shared.get("news_items") is not None:
                                _ns.set("shared_news_items", _shared["news_items"])
                            if _shared.get("x_feed") is not None:
                                _ns.set("shared_x_feed", _shared["x_feed"])
                        logger.debug("[session_manager] Injected shared research data into %d pod namespaces", len(self._pod_runtimes))

                    # 2. Run researcher cycles for all pods IN PARALLEL
                    async def _run_researcher(pod_id: str, runtime):
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

                    await asyncio.gather(
                        *[_run_researcher(pid, rt) for pid, rt in self._pod_runtimes.items()]
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
                        tick_sources = {}
                        latest_bar = None
                        bars_count = 0
                        for symbol in bars:
                            for bar in bars[symbol]:
                                try:
                                    await gateway.push_bar(bar)
                                    tick_prices[bar.symbol] = bar.close
                                    tick_sources[bar.symbol] = f"bar:{bar.source}"
                                    latest_bar = bar
                                    bars_count += 1
                                except Exception as e:
                                    logger.warning("[session_manager] push_bar failed for %s: %s", symbol, e)

                        if tick_prices:
                            accountant = runtime._ns.get("accountant")
                            if accountant:
                                accountant.mark_to_market(tick_prices, price_sources=tick_sources)
                            self._store_runtime_prices(runtime, tick_prices, tick_sources)

                        pod_latest_bars[pod_id] = latest_bar
                        logger.info("[session_manager] [iter %d] Pod %s: ingested %d bars, mark-to-market done",
                                    self._iteration, pod_id, bars_count)

                    # 5b. Position monitor — check for stop-loss / take-profit / max-hold breaches
                    await self._run_position_monitor()

                    # 5c. Loss review / intervention: evaluate before PMs can add new risk.
                    await self._refresh_loss_reviews()

                    # 5. Build cross-pod intelligence memos and run agent cycles
                    self._inject_firm_memos()
                    for pod_id, runtime in self._pod_runtimes.items():
                        bar = pod_latest_bars.get(pod_id)
                        if bar is None:
                            continue
                        try:
                            await runtime.run_cycle(bar, skip_researcher=True)
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
                                        "summary": f"{pod_id.upper()} PM: {summary_text}"[:500],
                                        "detail": detail_text,
                                    },
                                )
                                await self._event_bus.publish("agent.activity", activity_msg, publisher_id=f"{pod_id}.pm")
                            except Exception:
                                pass

                        except Exception as e:
                            logger.warning("[session_manager] [iter %d] Pod %s agent cycle failed: %s",
                                          self._iteration, pod_id, e)

                    # 3.5 Ingest closed trades into SourceAttributors and store
                    # dynamic source weights in each pod namespace for researcher use.
                    for pod_id, runtime in self._pod_runtimes.items():
                        attr = self._source_attributors.get(pod_id)
                        if attr:
                            try:
                                _acct = runtime._ns.get("accountant")
                                closed = _acct.closed_trades if _acct else []
                                if closed and attr:
                                    attr.ingest_batch(closed)
                                    runtime._ns.set("source_weights", attr.weights())
                                    logger.debug(
                                        "[session_manager] [iter %d] %s source weights updated: %s",
                                        self._iteration, pod_id, attr.weights(),
                                    )
                            except Exception as e:
                                logger.debug("[session_manager] source attribution update failed for %s: %s", pod_id, e)

                    # 4. Collect pod summaries for governance and emission
                    pod_summaries = await self._collect_pod_summaries()
                    logger.info("[session_manager] [iter %d] Collected %d pod summaries", self._iteration, len(pod_summaries))

                    # 4.0 Firm drawdown circuit breaker (vs peak NAV from memory)
                    total_firm_nav = 0.0
                    for s in pod_summaries.values():
                        rm = getattr(s, "risk_metrics", None)
                        if rm and getattr(rm, "nav", None) is not None:
                            total_firm_nav += float(rm.nav)
                    self._firm_peak_nav = max(self._firm_peak_nav, total_firm_nav)
                    if self._cro_agent and self._firm_peak_nav > 0:
                        dd_res = self._cro_agent.check_firm_drawdown(self._firm_peak_nav, total_firm_nav)
                        tier = dd_res.get("tier", "none")
                        for _pid, _rt in self._pod_runtimes.items():
                            _rt._ns.set("drawdown_halt", tier == "halt")
                            _rt._ns.set("drawdown_sizing_mult", 0.5 if tier == "orange" else 1.0)
                        if tier != "none" and dd_res.get("message"):
                            sev = (
                                "critical"
                                if tier == "halt"
                                else "warning"
                                if tier in ("yellow", "orange")
                                else "info"
                            )
                            if tier != self._last_drawdown_tier or self._iteration % 5 == 0:
                                try:
                                    dd_msg = AgentMessage(
                                        timestamp=datetime.now(timezone.utc),
                                        sender="cro",
                                        recipient="dashboard",
                                        topic="risk.alert",
                                        payload={
                                            "pod_id": "firm",
                                            "message": dd_res["message"],
                                            "severity": sev,
                                            "action": "firm_drawdown",
                                            "drawdown_tier": tier,
                                            "drawdown_pct": dd_res.get("drawdown_pct"),
                                        },
                                    )
                                    await self._event_bus.publish(
                                        "risk.alert", dd_msg, publisher_id="cro",
                                    )
                                except Exception as e:
                                    logger.debug("[session_manager] drawdown alert: %s", e)
                        self._last_drawdown_tier = tier

                    # Benchmark reference returns (non-blocking)
                    if self._iteration % 10 == 0 and self._benchmark_adapter and self._session_start:
                        try:
                            since = self._session_start.strftime("%Y-%m-%d")
                            self._benchmark_returns = await self._benchmark_adapter.fetch_all(since)
                        except Exception as e:
                            logger.debug("[session_manager] benchmark fetch: %s", e)

                    # 4.1. Compute firm-wide sector concentration and push to each pod namespace
                    firm_exposure = aggregate_exposure(pod_summaries)
                    for pod_id, runtime in self._pod_runtimes.items():
                        runtime._ns.set("firm_exposure", firm_exposure)
                    logger.debug("[session_manager] [iter %d] Firm exposure: %s", self._iteration,
                                 {k: f"{v:.1%}" for k, v in firm_exposure.items()})

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
                    if self._enable_web_server or self._web_app:
                        await self._update_web_state(pod_summaries)

                    # 5.6. Position aging enforcement — store alerts in namespace for PM next cycle
                    for pod_id, runtime in self._pod_runtimes.items():
                        try:
                            aging_alerts = check_aging(runtime._accountant)
                            if aging_alerts:
                                # Store in namespace for PM to pick up on next cycle
                                runtime._ns.set("aging_alerts", aging_alerts)
                                # Emit to EventBus for Intelligence Feed
                                for alert in aging_alerts:
                                    await self._event_bus.publish(
                                        topic=f"pod.{pod_id}.gateway",
                                        payload={
                                            "type": "position_aging_alert",
                                            "action": "position_aging_alert",
                                            "pod_id": pod_id,
                                            "symbol": alert["symbol"],
                                            "days_held": alert["days_held"],
                                            "max_hold_days": alert["max_hold_days"],
                                            "detail": (
                                                f"{alert['symbol']} held {alert['days_held']}d "
                                                f"(max {alert['max_hold_days']}d) — thesis reassessment required"
                                            ),
                                            "summary": f"Aging: {alert['symbol']} ({alert['days_held']}d)",
                                        }
                                    )
                            else:
                                # Clear stale aging alerts when no positions are overdue
                                runtime._ns.delete("aging_alerts")
                        except Exception as e:
                            logger.debug("[session_manager] aging check error %s: %s", pod_id, e)

                    # 6. Every N iterations: run governance cycle
                    if self._iteration > 0 and self._iteration % governance_freq == 0:
                        try:
                            # Inject pod intelligence briefs to CIO before governance
                            if hasattr(self, "_cio_agent") and self._cio_agent:
                                pod_briefs = self._build_pod_intelligence_briefs(pod_summaries)
                                self._cio_agent.set_pod_intelligence(pod_briefs)

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

                                # Accumulate governance decisions for memory persistence
                                self._governance_decisions.append({
                                    "ts": datetime.now(timezone.utc).isoformat(),
                                    "iteration": self._iteration,
                                    "narrative": mandate.narrative,
                                    "objectives": mandate.objectives,
                                    "rationale": mandate.rationale,
                                    "authorized_by": mandate.authorized_by,
                                    "cio_approved": mandate.cio_approved,
                                    "cro_approved": mandate.cro_approved,
                                    "pod_allocations": mandate.pod_allocations,
                                    "firm_nav": mandate.firm_nav,
                                    "cro_halt": mandate.cro_halt,
                                    "cro_halt_reason": mandate.cro_halt_reason,
                                    "breached_pods": breached_pods,
                                })

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

                            # Publish governance mandate to dashboard
                            try:
                                if mandate:
                                    mandate_payload = mandate.model_dump(mode="json")
                                    mandate_payload["event_type"] = "MANDATE_UPDATE"
                                    mandate_msg = AgentMessage(
                                        timestamp=datetime.now(timezone.utc),
                                        sender="governance.ceo",
                                        recipient="dashboard",
                                        topic="governance.ceo",
                                        payload=mandate_payload,
                                    )
                                    await self._event_bus.publish(
                                        "governance.ceo", mandate_msg, publisher_id="governance.ceo"
                                    )
                            except Exception:
                                pass

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
                                        "summary": gov_summary[:500],
                                        "detail": "",
                                    },
                                )
                                await self._event_bus.publish("agent.activity", gov_activity, publisher_id="governance")
                            except Exception:
                                pass

                            # Run capital reallocation after governance
                            await self._maybe_rebalance_capital(pod_summaries)

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

                    # 8. Persist session state to disk
                    self._save_memory()

                    # 9. Sleep
                    await asyncio.sleep(interval_seconds)

                except asyncio.CancelledError:
                    logger.info("[session_manager] Event loop cancelled")
                    break
                except Exception as exc:
                    logger.error("[session_manager] [iter %d] Event loop error: %s", self._iteration, exc)
                    # Continue running; don't exit on transient errors
                    await asyncio.sleep(interval_seconds)

        finally:
            ticker_task.cancel()
            try:
                await ticker_task
            except asyncio.CancelledError:
                pass
            if hasattr(self, "_research_ingestion") and self._research_ingestion:
                await self._research_ingestion.stop()
                self._research_ingestion.close()
            await self.stop_session()

    async def _run_price_ticker(self) -> None:
        """Background task: refresh live prices every 60 seconds.

        Runs independently of the main iteration loop so the dashboard always
        shows reasonably fresh prices and unrealized P&L.
        """
        await asyncio.sleep(5)
        while self._session_active:
            try:
                refresh = await self.refresh_live_position_prices_if_due(force=True)

                for pod_id, gateway in self._pod_gateways.items():
                    rt = self._pod_runtimes[pod_id]
                    try:
                        summary = await rt.get_summary()
                        await gateway.emit_summary(summary)
                    except Exception:
                        pass

                logger.info("[session_manager] Price ticker: refreshed %d prices across %d symbols",
                           refresh["updated_count"], refresh["live_symbol_count"])
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.warning("[session_manager] Price ticker failed (non-fatal): %s", e)

            await asyncio.sleep(60)

    async def refresh_live_position_prices_if_due(self, *, force: bool = False) -> dict:
        """Refresh open-position prices, throttled for dashboard/API callers."""
        now = time.monotonic()
        min_interval = float(getattr(self, "_position_price_refresh_min_interval_s", 20.0) or 20.0)
        last = float(getattr(self, "_last_position_price_refresh_at", 0.0) or 0.0)
        if not force and last and (now - last) < min_interval:
            return {
                "skipped": True,
                "reason": "recent",
                "updated_count": 0,
                "live_symbol_count": 0,
                "crypto_quote_count": 0,
            }

        lock = getattr(self, "_position_price_refresh_lock", None)
        if lock is None:
            lock = asyncio.Lock()
            self._position_price_refresh_lock = lock
        if lock.locked() and not force:
            return {
                "skipped": True,
                "reason": "in_progress",
                "updated_count": 0,
                "live_symbol_count": 0,
                "crypto_quote_count": 0,
            }

        async with lock:
            now = time.monotonic()
            last = float(getattr(self, "_last_position_price_refresh_at", 0.0) or 0.0)
            if not force and last and (now - last) < min_interval:
                return {
                    "skipped": True,
                    "reason": "recent",
                    "updated_count": 0,
                    "live_symbol_count": 0,
                    "crypto_quote_count": 0,
                }
            refresh = await self._refresh_live_position_prices()
            self._last_position_price_refresh_at = time.monotonic()
            return refresh

    @staticmethod
    def _dict_by_symbol_alias(rows: dict[str, dict]) -> dict[str, dict]:
        indexed: dict[str, dict] = {}
        for symbol, row in (rows or {}).items():
            for alias in symbol_aliases(symbol):
                indexed.setdefault(alias, row)
        return indexed

    @staticmethod
    def _lookup_symbol_alias(rows_by_alias: dict[str, dict], symbol: str) -> dict | None:
        for alias in symbol_aliases(symbol):
            if alias in rows_by_alias:
                return rows_by_alias[alias]
        return None

    @staticmethod
    def _valid_price(value) -> float | None:
        try:
            price = float(value)
        except Exception:
            return None
        return price if price > 0 else None

    def _held_crypto_symbols(self) -> set[str]:
        held_crypto_symbols: set[str] = set()
        for rt in self._pod_runtimes.values():
            acct = rt._ns.get("accountant")
            if not acct:
                continue
            for sym, pos_data in acct._positions.items():
                if pos_data.get("quantity", 0) != 0 and is_crypto_symbol(sym):
                    held_crypto_symbols.add(canonical_crypto_symbol(sym))
        return held_crypto_symbols

    async def _fetch_crypto_position_quotes(self, symbols: set[str]) -> dict[str, dict]:
        """Fetch crypto marks from broker market data first, then external quote service."""
        if not symbols:
            return {}

        ordered = sorted(symbols)
        quotes: dict[str, dict] = {}
        errors: list[str] = []

        alpaca_fetch = getattr(self._alpaca, "fetch_crypto_quotes", None)
        if callable(alpaca_fetch):
            try:
                broker_quotes = await asyncio.wait_for(alpaca_fetch(ordered), timeout=3.5)
                if broker_quotes:
                    quotes.update(broker_quotes)
            except asyncio.TimeoutError:
                errors.append("Alpaca crypto quote fetch timed out")
            except Exception as exc:
                errors.append(f"Alpaca crypto quote fetch failed: {exc}")

        quotes_by_alias = self._dict_by_symbol_alias(quotes)
        missing = [
            symbol for symbol in ordered
            if self._lookup_symbol_alias(quotes_by_alias, symbol) is None
        ]

        price_service = getattr(self, "_price_service", None)
        if price_service and missing:
            try:
                service_quotes = await asyncio.wait_for(
                    price_service.get_quotes(missing),
                    timeout=6.0,
                )
                if service_quotes:
                    quotes.update(service_quotes)
            except asyncio.TimeoutError:
                errors.append("Crypto quote fallback timed out")
            except Exception as exc:
                errors.append(f"Crypto quote fallback failed: {exc}")

        for error in errors:
            logger.debug("[session_manager] %s", error)
        return quotes

    async def _refresh_live_position_prices(self) -> dict:
        """Refresh accountant marks from broker positions plus crypto quote fallback."""
        held_crypto_symbols = self._held_crypto_symbols()

        live, live_error = await self._broker_diagnostic_call(
            "Position price refresh",
            self._alpaca.get_open_positions(),
            {},
        )
        if live_error:
            logger.debug("[session_manager] %s", live_error)
        live_by_alias = self._dict_by_symbol_alias(live)

        crypto_quotes = await self._fetch_crypto_position_quotes(held_crypto_symbols)
        crypto_quotes_by_alias = self._dict_by_symbol_alias(crypto_quotes)

        updated_count = 0
        for rt in self._pod_runtimes.values():
            acct = rt._ns.get("accountant")
            if not acct:
                continue
            tick_prices: dict[str, float] = {}
            price_sources: dict[str, str] = {}
            for sym, pos_data in acct._positions.items():
                if pos_data.get("quantity", 0) == 0:
                    continue

                broker_pos = self._lookup_symbol_alias(live_by_alias, sym)
                broker_price = self._valid_price((broker_pos or {}).get("current_price"))
                if broker_price is not None:
                    tick_prices[sym] = broker_price
                    price_sources[sym] = "alpaca"

                if is_crypto_symbol(sym):
                    quote = self._lookup_symbol_alias(crypto_quotes_by_alias, sym)
                    quote_price = self._valid_price((quote or {}).get("price"))
                    if quote_price is not None:
                        tick_prices[sym] = quote_price
                        price_sources[sym] = str(quote.get("source") or "crypto_quote")

            if tick_prices:
                acct.mark_to_market(tick_prices, price_sources=price_sources)
                self._store_runtime_prices(rt, tick_prices, price_sources)
                updated_count += len(tick_prices)

        return {
            "updated_count": updated_count,
            "live_symbol_count": len(live or {}),
            "crypto_quote_count": len(crypto_quotes or {}),
            "errors": [live_error] if live_error else [],
        }

    def _store_runtime_prices(
        self,
        runtime,
        prices: dict[str, float],
        price_sources: dict[str, str] | None = None,
    ) -> None:
        """Keep the pod namespace aligned with the latest mark-to-market prices."""
        if not runtime or not prices:
            return
        price_sources = price_sources or {}
        now_iso = datetime.now(timezone.utc).isoformat()
        last_prices = dict(runtime._ns.get("last_prices") or {})
        last_sources = dict(runtime._ns.get("last_price_sources") or {})
        last_updated = dict(runtime._ns.get("last_price_updated_at") or {})
        for symbol, price in prices.items():
            try:
                numeric_price = float(price)
            except (TypeError, ValueError):
                continue
            if numeric_price <= 0:
                continue
            last_prices[symbol] = numeric_price
            last_sources[symbol] = price_sources.get(symbol) or "market"
            last_updated[symbol] = now_iso
        runtime._ns.set("last_prices", last_prices)
        runtime._ns.set("last_price_sources", last_sources)
        runtime._ns.set("last_price_updated_at", last_updated)

    async def _maybe_run_position_review(self) -> None:
        """Run position review if the date has changed since last review."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if today == self._last_review_date:
            return

        if not self._position_reviewer:
            return

        # Check if any pod has open positions
        pod_accountants = {}
        for pod_id, runtime in self._pod_runtimes.items():
            acct = runtime._ns.get("accountant")
            if acct and acct.current_positions:
                pod_accountants[pod_id] = acct

        if not pod_accountants:
            logger.info("[session_manager] No open positions — skipping daily review")
            self._last_review_date = today
            return

        logger.info("[session_manager] Running daily position review for %d pod(s)", len(pod_accountants))

        try:
            review_result = await self._position_reviewer.run_review(
                pod_runtimes=self._pod_runtimes,
                pod_accountants=pod_accountants,
            )

            if not review_result.get("reviewed"):
                self._last_review_date = today
                return

            # Execute agreed actions through risk pipeline
            for pod_id, pod_result in review_result.get("pods", {}).items():
                actions = pod_result.get("actions", [])
                if not actions:
                    continue
                orders = self._position_reviewer.build_orders(actions, pod_id)
                if orders:
                    runtime = self._pod_runtimes.get(pod_id)
                    if runtime:
                        exec_results = await runtime.execute_review_orders(orders)
                        logger.info("[session_manager] Review orders for %s: %s", pod_id, exec_results)

            # Generate report
            await self._generate_review_report(review_result)

            self._last_review_date = today
            logger.info("[session_manager] Daily position review complete")

        except Exception as e:
            logger.error("[session_manager] Position review failed: %s", e, exc_info=True)
            self._last_review_date = today

    async def _generate_review_report(self, review_result: dict) -> None:
        """Generate an HTML report after position review and save to reports dir."""
        try:
            from src.reports.daily_report import DailyReportGenerator

            pods_data = {}
            for pid, runtime in self._pod_runtimes.items():
                try:
                    summary = await runtime.get_summary()
                    pods_data[pid] = summary.model_dump(mode="json") if hasattr(summary, "model_dump") else {}
                except Exception:
                    pods_data[pid] = {}

            # Build review dialogue list for the report
            review_dialogue = []
            for pod_id, pod_result in review_result.get("pods", {}).items():
                if isinstance(pod_result, dict) and "error" not in pod_result:
                    review_dialogue.append({
                        "pod_id": pod_id,
                        "positions_reviewed": pod_result.get("positions_reviewed", 0),
                        "cio_challenge": pod_result.get("cio_challenge", ""),
                        "pm_response": pod_result.get("pm_response", ""),
                        "cio_decisions": pod_result.get("cio_decisions", ""),
                        "actions": pod_result.get("actions", []),
                        "summary": pod_result.get("summary", ""),
                    })

            perf_data, pos_data, sq_data, events_data = self._collect_report_data()

            report_gen = DailyReportGenerator()
            report_html = report_gen.generate(
                session_dir=self._session_logger.session_dir if self._session_logger else "",
                session_start=getattr(self, "_session_start", None),
                session_end=datetime.now(),
                pods_data=pods_data,
                trades=self._session_logger._fill_log if self._session_logger else [],
                governance=getattr(self, "_governance_decisions", []),
                firm_nav=sum(p.get("risk_metrics", {}).get("nav", 0) for p in pods_data.values()),
                initial_capital=sum(p.get("risk_metrics", {}).get("starting_capital", 0) for p in pods_data.values()),
                review_dialogue=review_dialogue,
                performance_data=perf_data,
                positions_data=pos_data,
                signal_quality_data=sq_data,
                upcoming_events=events_data,
            )

            report_gen.generate_markdown(
                session_dir=self._reports_dir,
                pods_data=pods_data,
                trades=self._session_logger._fill_log if self._session_logger else [],
                firm_nav=sum(p.get("risk_metrics", {}).get("nav", 0) for p in pods_data.values()),
                initial_capital=sum(p.get("risk_metrics", {}).get("starting_capital", 0) for p in pods_data.values()),
                performance_data=perf_data,
                positions_data=pos_data,
                signal_quality_data=sq_data,
            )

            # Save report
            os.makedirs(self._reports_dir, exist_ok=True)
            filename = f"review_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            filepath = os.path.join(self._reports_dir, filename)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(report_html)
            logger.info("[session_manager] Review report saved: %s", filepath)

            # Prune old reports (keep max 5)
            report_files = sorted(
                Path(self._reports_dir).glob("review_*.html"),
                key=lambda f: f.stat().st_mtime,
                reverse=True,
            )
            for old_file in report_files[5:]:
                try:
                    old_file.unlink()
                    logger.info("[session_manager] Pruned old report: %s", old_file.name)
                except Exception:
                    pass

            # Broadcast new report event via WebSocket
            try:
                report_msg = AgentMessage(
                    timestamp=datetime.now(timezone.utc),
                    sender="reports",
                    recipient="dashboard",
                    topic="agent.activity",
                    payload={
                        "agent_id": "reports",
                        "agent_role": "SYSTEM",
                        "pod_id": "firm",
                        "action": "new_report",
                        "summary": f"Position review report generated: {filename}",
                        "detail": "",
                        "filename": filename,
                    },
                )
                await self._event_bus.publish("agent.activity", report_msg, publisher_id="reports")
            except Exception:
                pass

        except Exception as e:
            logger.warning("[session_manager] Review report generation failed: %s", e)

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

    def _collect_report_data(self) -> tuple[dict, dict, dict, list]:
        """Collect performance, positions, signal quality, and events for reports."""
        perf_data: dict = {}
        pos_data: dict = {}
        sq_data: dict = {}
        events_data: list = []
        today = datetime.now(timezone.utc).date()

        for pod_id, runtime in self._pod_runtimes.items():
            ns = runtime._ns if hasattr(runtime, "_ns") else None
            if not ns:
                continue

            perf = ns.get("performance_summary")
            if perf:
                perf_data[pod_id] = perf

            accountant = ns.get("accountant")
            if accountant:
                pod_positions = []
                for sym, snap in accountant.current_positions.items():
                    meta = accountant._entry_metadata.get(sym, {})
                    entry_time = meta.get("entry_time", "")
                    days_held = 0
                    if entry_time:
                        try:
                            days_held = (today - datetime.fromisoformat(entry_time).date()).days
                        except (ValueError, TypeError):
                            pass
                    pod_positions.append({
                        "symbol": sym,
                        "qty": snap.qty,
                        "cost_basis": snap.cost_basis,
                        "current_price": snap.current_price,
                        "unrealized_pnl": snap.unrealized_pnl,
                        "pnl_pct": snap.pnl_pct,
                        "days_held": days_held,
                        "stop_loss_pct": meta.get("stop_loss_pct", 0.05),
                        "take_profit_pct": meta.get("take_profit_pct", 0.15),
                        "entry_thesis": (
                            snap.entry_thesis
                            or meta.get("entry_thesis")
                            or meta.get("reasoning", "")
                        ),
                    })
                if pod_positions:
                    pos_data[pod_id] = pod_positions

            scorer = getattr(runtime, "_signal_scorer", None)
            if scorer:
                sq_text = scorer.format_for_prompt()
                if sq_text:
                    sq_data[pod_id] = sq_text

            events = ns.get("upcoming_events")
            if events:
                events_data.extend(events)

        return perf_data, pos_data, sq_data, events_data

    async def _run_position_monitor(self) -> None:
        """Check all pod positions for stop-loss / take-profit / max-hold breaches."""
        for pod_id, runtime in self._pod_runtimes.items():
            accountant = runtime._ns.get("accountant")
            if not accountant:
                continue
            try:
                exit_orders = self._position_monitor.check_positions(accountant)
                if exit_orders:
                    for eo in exit_orders:
                        exit_ctx = {
                            "approved_order": eo,
                            "mandate": runtime._ns.get("governance_mandate"),
                            "risk_halt": False,
                            "auto_exit": True,
                        }
                        try:
                            await runtime._exec_trader.run_cycle(exit_ctx)
                            logger.info("[session_manager] Position monitor auto-exit: %s %s %.4f in %s",
                                        eo.side.value, eo.symbol, eo.quantity, pod_id)
                            activity_msg = AgentMessage(
                                timestamp=datetime.now(timezone.utc),
                                sender="position_monitor",
                                recipient="dashboard",
                                topic="agent.activity",
                                payload={
                                    "agent_id": "position_monitor",
                                    "agent_role": "PositionMonitor",
                                    "pod_id": pod_id,
                                    "action": "position_monitor_exit",
                                    "summary": f"Auto-exit: {eo.side.value} {eo.quantity:.4f} {eo.symbol}",
                                    "detail": f"Position breached exit condition in {pod_id}",
                                },
                            )
                            await self._event_bus.publish("agent.activity", activity_msg, publisher_id="position_monitor")
                        except Exception as e:
                            logger.warning("[session_manager] Position monitor exit failed for %s/%s: %s", pod_id, eo.symbol, e)
            except Exception as e:
                logger.warning("[session_manager] Position monitor check failed for %s: %s", pod_id, e)

    def _inject_firm_memos(self) -> None:
        """Build cross-pod intelligence memos and inject into each pod's namespace.

        Each pod gets a memo showing macro views from all OTHER pods,
        so PMs can see what other desks are thinking without crossing
        the pod isolation boundary for positions or signals.
        """
        views: dict[str, dict] = {}
        for pod_id, runtime in self._pod_runtimes.items():
            view = runtime._ns.get("macro_view")
            if view:
                views[pod_id] = view

        if len(views) < 2:
            return

        for pod_id, runtime in self._pod_runtimes.items():
            other_views = [v for pid, v in views.items() if pid != pod_id]
            if not other_views:
                continue
            lines = ["Cross-pod intelligence (other desks):"]
            for v in other_views:
                lines.append(
                    f"  {v.get('pod_id', '?').upper()}: "
                    f"regime={v.get('regime', '?')}, "
                    f"outlook={v.get('outlook', '?')}, "
                    f"action={v.get('action', 'holding')}"
                )
            runtime._ns.set("firm_memo", "\n".join(lines))

    async def _maybe_rebalance_capital(self, pod_summaries: dict) -> None:
        """Run after governance cycle — rebalance capital based on pod performance scores."""
        try:
            # Score all pods
            pod_scores = {}
            for pod_id, summary in pod_summaries.items():
                perf  = (getattr(summary, "performance_metrics", None) or {})
                stats = (getattr(summary, "trade_outcome_stats",  None) or {})
                if isinstance(perf, dict) and isinstance(stats, dict):
                    pod_scores[pod_id] = score_pod(pod_id, perf, stats).score

            if not pod_scores or not self._allocator:
                return

            # Suggest new allocations
            new_allocs = self._allocator.suggest_reallocation(
                pod_scores, min_pct=0.15, max_pct=0.40,
            )
            firm_nav = sum(
                (s.risk_metrics.nav if (s.risk_metrics and s.risk_metrics.nav) else 0.0)
                for s in pod_summaries.values()
            )
            if firm_nav <= 0:
                return

            # Apply: transfer available cash, set trim/growth targets
            for pod_id, new_pct in new_allocs.items():
                runtime = self._pod_runtimes.get(pod_id)
                if not runtime:
                    continue
                target_capital = new_pct * firm_nav
                current_summary = pod_summaries.get(pod_id, None)
                current_nav = current_summary.risk_metrics.nav if (current_summary and current_summary.risk_metrics) else 0.0
                delta = target_capital - current_nav

                if delta < -10.0:
                    # Pod needs to shrink — transfer available cash, mark trim target
                    acct_rb = runtime._ns.get("accountant")
                    available_cash = getattr(acct_rb, "_cash", 0.0) if acct_rb else 0.0
                    transfer = min(available_cash, abs(delta))
                    if transfer > 1.0 and acct_rb:
                        acct_rb._cash -= transfer
                        logger.info("[realloc] %s -> trim $%.2f (target $%.2f)", pod_id, transfer, target_capital)
                    runtime._ns.set("trim_target_capital", round(target_capital, 2))
                    # Clear any stale growth target
                    runtime._ns.delete("growth_target_capital")

                elif delta > 10.0:
                    # Pod should grow — mark growth target
                    runtime._ns.set("growth_target_capital", round(target_capital, 2))
                    # Clear any stale trim target
                    runtime._ns.delete("trim_target_capital")
                    logger.info("[realloc] %s -> grow target $%.2f (delta +$%.2f)", pod_id, target_capital, delta)
                else:
                    # Within tolerance — clear any stale directives
                    runtime._ns.delete("trim_target_capital")
                    runtime._ns.delete("growth_target_capital")

            # Update allocator percentages
            self._allocator._allocations.update(new_allocs)
            logger.info("[realloc] Capital reallocation applied: %s", new_allocs)

        except Exception as e:
            logger.warning("[session_manager] reallocation error: %s", e)

    async def _reconcile_positions(self) -> None:
        """Compare Alpaca positions against per-pod accountant positions.

        Alpaca tracks aggregate positions (not per-pod), so this is
        best-effort.  Discrepancies are logged as warnings, not auto-corrected.
        Also cancels stale open orders (pending > 60s).
        """
        try:
            alpaca_positions = await self._alpaca.get_open_positions()
            alpaca_positions_by_alias = self._dict_by_symbol_alias(alpaca_positions)
            for pod_id, runtime in self._pod_runtimes.items():
                accountant = runtime._ns.get("accountant")
                if not accountant:
                    continue
                for symbol, snapshot in accountant.current_positions.items():
                    alpaca_pos = self._lookup_symbol_alias(alpaca_positions_by_alias, symbol)
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
            await self.reconcile_execution_state()
        except Exception as e:
            logger.debug("[reconcile] Stale order cleanup skipped: %s", e)

    @staticmethod
    def _signed_broker_qty(position: dict) -> float:
        qty = float((position or {}).get("qty") or 0.0)
        side = str((position or {}).get("side") or "long").lower()
        return -abs(qty) if side == "short" else abs(qty)

    @staticmethod
    def _order_age_seconds(submitted_at, now: datetime) -> float | None:
        if not submitted_at:
            return None
        try:
            if isinstance(submitted_at, str):
                submitted = datetime.fromisoformat(submitted_at.replace("Z", "+00:00"))
            else:
                submitted = submitted_at
            if submitted.tzinfo is None:
                submitted = submitted.replace(tzinfo=timezone.utc)
            return (now - submitted.astimezone(timezone.utc)).total_seconds()
        except Exception:
            return None

    def _local_positions_by_symbol(self) -> dict[str, dict]:
        local: dict[str, dict] = {}
        for pod_id, runtime in self._pod_runtimes.items():
            accountant = runtime._ns.get("accountant")
            if not accountant:
                continue
            for symbol, snap in accountant.current_positions.items():
                qty = float(getattr(snap, "qty", 0.0) or 0.0)
                if abs(qty) <= 1e-9:
                    continue
                current_price = float(getattr(snap, "current_price", 0.0) or 0.0)
                notional = abs(qty * current_price)
                row = local.setdefault(
                    symbol,
                    {"symbol": symbol, "qty": 0.0, "notional": 0.0, "pods": []},
                )
                row["qty"] += qty
                row["notional"] += notional
                row["pods"].append({
                    "pod_id": pod_id,
                    "qty": qty,
                    "current_price": current_price,
                    "notional": notional,
                })
        return local

    async def _broker_diagnostic_call(self, label: str, awaitable, default):
        """Run a broker diagnostic read without letting the dashboard hang."""
        timeout_s = max(0.1, float(getattr(self, "_broker_reconciliation_timeout_s", 2.5) or 2.5))
        try:
            return await asyncio.wait_for(awaitable, timeout=timeout_s), None
        except asyncio.TimeoutError:
            return default, f"{label} timed out after {timeout_s:.1f}s"
        except Exception as exc:
            return default, f"{label} failed: {exc}"

    async def get_broker_reconciliation(self) -> dict:
        """Return a local-vs-Alpaca reconciliation payload for the dashboard."""
        generated_at = datetime.now(timezone.utc).isoformat()
        errors: list[str] = []

        (account, account_error), (broker_positions, position_error), (open_orders, order_error) = await asyncio.gather(
            self._broker_diagnostic_call("Account fetch", self._alpaca.fetch_account(), {}),
            self._broker_diagnostic_call("Position fetch", self._alpaca.get_open_positions(), {}),
            self._broker_diagnostic_call("Open order fetch", self._alpaca.get_all_open_orders(), []),
        )
        errors.extend(e for e in (account_error, position_error, order_error) if e)

        local_positions = self._local_positions_by_symbol()
        local_by_alias = self._dict_by_symbol_alias(local_positions)
        broker_rows: dict[str, dict] = {}
        for broker_symbol, broker in (broker_positions or {}).items():
            local_match = self._lookup_symbol_alias(local_by_alias, broker_symbol)
            display_symbol = (
                local_match.get("symbol")
                if local_match
                else canonical_crypto_symbol(broker_symbol) if is_crypto_symbol(broker_symbol) else broker_symbol
            )
            row = dict(broker)
            row["_broker_symbol"] = broker_symbol
            broker_rows[display_symbol] = row

        rows: list[dict] = []
        mismatches: list[dict] = []
        for symbol in sorted(set(local_positions) | set(broker_rows)):
            local = local_positions.get(
                symbol,
                {"symbol": symbol, "qty": 0.0, "notional": 0.0, "pods": []},
            )
            broker = broker_rows.get(symbol, {})
            local_qty = float(local.get("qty") or 0.0)
            broker_qty = self._signed_broker_qty(broker) if broker else 0.0
            delta = broker_qty - local_qty
            status = "OK"
            if broker and symbol not in local_positions:
                status = "BROKER_ONLY"
            elif symbol in local_positions and not broker:
                status = "LOCAL_ONLY"
            elif abs(delta) > 0.01:
                status = "QTY_MISMATCH"

            row = {
                "symbol": symbol,
                "status": status,
                "local_qty": round(local_qty, 6),
                "broker_qty": round(broker_qty, 6),
                "qty_delta": round(delta, 6),
                "local_notional": round(float(local.get("notional") or 0.0), 4),
                "broker_price": broker.get("current_price"),
                "broker_unrealized_pl": broker.get("unrealized_pl"),
                "broker_symbol": broker.get("_broker_symbol", symbol),
                "pods": local.get("pods", []),
            }
            rows.append(row)
            if status != "OK":
                mismatches.append(row)

        payload = {
            "generated_at": generated_at,
            "account": account or {},
            "positions": rows,
            "mismatches": mismatches,
            "open_orders": open_orders or [],
            "errors": errors,
            "status": "OK" if not mismatches and not errors else "CHECK",
            "source": "live_broker" if not errors else "partial_broker",
        }
        self._last_broker_reconciliation = payload
        return payload

    @staticmethod
    def _position_price_age_seconds(price_updated_at: str | None) -> float | None:
        if not price_updated_at:
            return None
        try:
            ts = datetime.fromisoformat(str(price_updated_at).replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - ts.astimezone(timezone.utc)).total_seconds()
        except Exception:
            return None

    def get_data_quality_report(self) -> dict:
        """Return market-data freshness and notional integrity diagnostics."""
        rows: list[dict] = []
        failures: list[dict] = []
        for pod_id, runtime in self._pod_runtimes.items():
            acct = runtime._ns.get("accountant")
            if not acct:
                continue
            for symbol, snap in acct.current_positions.items():
                qty = float(getattr(snap, "qty", 0.0) or 0.0)
                current_price = float(getattr(snap, "current_price", 0.0) or 0.0)
                cost_basis = float(getattr(snap, "cost_basis", 0.0) or 0.0)
                current_notional = abs(float(getattr(snap, "current_notional", qty * current_price) or 0.0))
                entry_notional = abs(float(getattr(snap, "entry_notional", qty * cost_basis) or 0.0))
                price_source = str(getattr(snap, "price_source", "") or "")
                price_updated_at = str(getattr(snap, "price_updated_at", "") or "")
                price_age_s = self._position_price_age_seconds(price_updated_at)
                issues: list[str] = []
                if current_price <= 0:
                    issues.append("missing current price")
                if not price_source:
                    issues.append("missing price source")
                if not price_updated_at:
                    issues.append("missing price timestamp")
                if bool(getattr(snap, "price_stale", False)):
                    issues.append("stale price")
                if current_notional <= 0:
                    issues.append("missing current notional")
                if entry_notional <= 0:
                    issues.append("missing entry notional")
                rows.append({
                    "pod_id": pod_id,
                    "symbol": symbol,
                    "status": "OK" if not issues else "CHECK",
                    "issues": issues,
                    "qty": round(qty, 8),
                    "cost_basis": round(cost_basis, 8),
                    "current_price": round(current_price, 8),
                    "entry_notional": round(entry_notional, 4),
                    "current_notional": round(current_notional, 4),
                    "price_source": price_source,
                    "price_updated_at": price_updated_at,
                    "price_age_seconds": round(price_age_s, 1) if price_age_s is not None else None,
                    "price_stale": bool(getattr(snap, "price_stale", False)),
                })

            for failure in list(runtime._ns.get("data_quality_failures") or [])[:20]:
                if isinstance(failure, dict):
                    item = dict(failure)
                    item.setdefault("pod_id", pod_id)
                    failures.append(item)

        broker = self._last_broker_reconciliation or {}
        mismatch_count = len(broker.get("mismatches", []) or []) if broker else None
        stale_count = sum(1 for row in rows if row.get("price_stale"))
        missing_source_count = sum(1 for row in rows if not row.get("price_source"))
        missing_notional_count = sum(1 for row in rows if row.get("current_notional", 0) <= 0)
        check_count = sum(1 for row in rows if row.get("status") != "OK")
        status = "OK" if check_count == 0 and not failures else "CHECK"
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "position_count": len(rows),
            "check_count": check_count,
            "stale_price_count": stale_count,
            "missing_source_count": missing_source_count,
            "missing_notional_count": missing_notional_count,
            "blocked_trade_count": len(failures),
            "broker_mismatch_count": mismatch_count,
            "positions": rows,
            "recent_failures": failures[:20],
        }

    def _held_symbols_by_pod(self) -> dict[str, list[str]]:
        held: dict[str, list[str]] = {}
        for pod_id, runtime in self._pod_runtimes.items():
            acct = runtime._ns.get("accountant")
            symbols = []
            if acct:
                symbols = [str(symbol).upper() for symbol in acct.current_positions.keys()]
            held[pod_id] = symbols
        return held

    def _research_action_events(self, listener_state: dict | None = None) -> list[dict]:
        listener_state = listener_state or {}
        events: list[dict] = []

        for bucket in ("recent_activity", "recent_orders", "recent_trades", "recent_governance"):
            for msg in listener_state.get(bucket, []) or []:
                data = msg.get("data", {}) if isinstance(msg, dict) else {}
                if not isinstance(data, dict):
                    continue
                text = " ".join(str(data.get(k, "")) for k in (
                    "summary", "detail", "reason", "reasoning", "decision", "symbol", "side", "action"
                ))
                events.append({
                    "ts": msg.get("timestamp") or data.get("timestamp") or data.get("submitted_at"),
                    "kind": bucket,
                    "pod_id": str(data.get("pod_id") or ("firm" if bucket == "recent_governance" else "")).lower(),
                    "symbol": str(data.get("symbol") or "").upper(),
                    "action": str(data.get("action") or data.get("side") or data.get("decision") or bucket),
                    "status": str(data.get("status") or "INFO").upper(),
                    "text": text,
                })

        if not events and self._audit_log:
            try:
                for msg in self._audit_log.recent_messages(limit=200):
                    payload = msg.get("payload") or {}
                    if not isinstance(payload, dict):
                        continue
                    text = " ".join(str(payload.get(k, "")) for k in (
                        "summary", "detail", "reason", "reasoning", "decision", "symbol", "side", "action"
                    ))
                    events.append({
                        "ts": msg.get("timestamp"),
                        "kind": msg.get("topic", "audit"),
                        "pod_id": str(payload.get("pod_id") or "").lower(),
                        "symbol": str(payload.get("symbol") or "").upper(),
                        "action": str(payload.get("action") or payload.get("side") or payload.get("decision") or msg.get("topic", "")),
                        "status": str(payload.get("status") or "INFO").upper(),
                        "text": text,
                    })
            except Exception:
                pass
        return events

    def _research_action_audit(self, item: dict, events: list[dict]) -> dict:
        asset_classes = {str(v).lower() for v in item.get("asset_classes", [])}
        tickers = {str(v).upper() for v in item.get("tickers", [])}
        factors = {str(v).lower() for v in item.get("factors", [])}
        text_needles = tickers | {f.upper() for f in factors}

        matched = []
        for event in events:
            pod = event.get("pod_id", "")
            symbol = event.get("symbol", "")
            event_text = str(event.get("text", "")).upper()
            pod_match = pod in asset_classes or (pod == "firm" and bool(asset_classes))
            symbol_match = bool(symbol and symbol in tickers)
            text_match = any(needle and needle in event_text for needle in text_needles)
            if pod_match or symbol_match or text_match:
                matched.append({
                    "ts": event.get("ts"),
                    "kind": event.get("kind"),
                    "pod_id": pod,
                    "symbol": symbol,
                    "action": event.get("action"),
                    "status": event.get("status"),
                })
            if len(matched) >= 5:
                break

        urgency = float(item.get("urgency") or 0.0)
        if matched:
            status = "acted"
            next_action = "Recent agent/order activity references the same pod, factor, or symbol."
        elif urgency >= 0.65:
            status = "needs_review"
            next_action = "High-urgency item has no matching recent agent action."
        else:
            status = "monitor"
            next_action = "Monitor unless it becomes position-relevant or urgency rises."

        return {
            "status": status,
            "matched_events": matched,
            "next_action": next_action,
        }

    def get_research_feed_report(self, limit: int = 100, listener_state: dict | None = None) -> dict:
        """Return persistent research feed, source health, routing, and action audit."""
        generated_at = datetime.now(timezone.utc).isoformat()
        if not hasattr(self, "_research_ingestion") or not self._research_ingestion:
            return {
                "generated_at": generated_at,
                "items": [],
                "sources": [],
                "item_count": 0,
                "source_count": 0,
                "held_symbols_by_pod": self._held_symbols_by_pod(),
                "status": "NO_INGESTION",
                "last_fetch_time": None,
            }

        report = self._research_ingestion.get_research_feed_summary(limit=limit)
        held_by_pod = self._held_symbols_by_pod()
        held_all = {sym for symbols in held_by_pod.values() for sym in symbols}
        events = self._research_action_events(listener_state)

        for item in report.get("items", []):
            tickers = {str(v).upper() for v in item.get("tickers", [])}
            item["held_symbols"] = sorted(tickers & held_all)
            item["affected_pods"] = [
                pod_id for pod_id in POD_IDS
                if pod_id in {str(v).lower() for v in item.get("asset_classes", [])}
            ]
            if not item["affected_pods"] and "macro" in {str(v).lower() for v in item.get("asset_classes", [])}:
                item["affected_pods"] = list(POD_IDS)
            item["action_audit"] = self._research_action_audit(item, events)

        source_errors = sum(1 for source in report.get("sources", []) if source.get("status") not in {"ok", "cached", "success"})
        status = "OK" if source_errors == 0 else "CHECK"
        return {
            **report,
            "generated_at": generated_at,
            "held_symbols_by_pod": held_by_pod,
            "status": status,
            "source_error_count": source_errors,
            "last_fetch_time": self._research_ingestion.last_fetch_time.isoformat() if self._research_ingestion.last_fetch_time else None,
        }

    async def get_state_health(self) -> dict:
        """Return state-integrity diagnostics for the dashboard."""
        generated_at = datetime.now(timezone.utc).isoformat()
        data_quality = self.get_data_quality_report()
        nav_history = self._nav_store.health_summary() if self._nav_store else {
            "total_rows": 0,
            "repaired_rows": 0,
            "quality_counts": {},
            "first_ts": None,
            "last_ts": None,
            "latest_by_pod": {},
        }
        broker_status = {
            "status": "UNKNOWN",
            "mismatch_count": None,
            "open_order_count": None,
            "errors": [],
        }
        broker = self._last_broker_reconciliation or {}
        if broker:
            broker_status = {
                "status": broker.get("status", "UNKNOWN"),
                "mismatch_count": len(broker.get("mismatches", []) or []),
                "open_order_count": len(broker.get("open_orders", []) or []),
                "errors": broker.get("errors", []) or [],
                "cached_at": broker.get("generated_at"),
            }

        pods: list[dict] = []
        latest_nav = nav_history.get("latest_by_pod", {}) or {}
        for pod_id in POD_IDS:
            runtime = self._pod_runtimes.get(pod_id)
            acct = runtime._ns.get("accountant") if runtime else None
            state = acct.to_state_dict() if acct else {}
            nav = float(state.get("nav") or 0.0)
            starting_capital = float(state.get("starting_capital") or self._pod_capital.get(pod_id) or self._capital_per_pod or 0.0)
            cash = float(state.get("cash") or 0.0)
            invested = float(state.get("invested") or max(0.0, nav - cash))
            positions = state.get("positions", []) or []
            nav_row = latest_nav.get(pod_id, {})
            issues: list[str] = []
            if starting_capital <= 0:
                issues.append("Missing starting capital")
            if nav <= 0 and self._session_active:
                issues.append("Missing live NAV")
            if nav_row and nav_row.get("quality") not in (None, "ok"):
                issues.append(f"Latest NAV row was {nav_row.get('quality')}")
            status = "OK" if not issues else "CHECK"
            pods.append({
                "pod_id": pod_id,
                "status": status,
                "issues": issues,
                "starting_capital": round(starting_capital, 4),
                "allocated_capital": round(float(self._pod_capital.get(pod_id) or self._capital_per_pod or starting_capital), 4),
                "nav": round(nav, 4),
                "cash": round(cash, 4),
                "invested": round(invested, 4),
                "position_count": len(positions),
                "last_nav_ts": nav_row.get("ts"),
                "last_nav_quality": nav_row.get("quality", "unknown"),
            })

        overall_status = "OK"
        warnings: list[str] = []
        if nav_history.get("repaired_rows", 0):
            overall_status = "CHECK"
            warnings.append(f"{nav_history.get('repaired_rows')} NAV history row(s) repaired for chart integrity")
        if broker_status.get("status") == "CHECK":
            overall_status = "CHECK"
            warnings.append("Broker/local reconciliation needs review")
        if data_quality.get("status") == "CHECK":
            overall_status = "CHECK"
            warnings.append("Market data quality needs review")
        for pod in pods:
            if pod["status"] != "OK":
                overall_status = "CHECK"
                warnings.extend([f"{pod['pod_id']}: {issue}" for issue in pod["issues"]])

        return {
            "generated_at": generated_at,
            "status": overall_status,
            "warnings": warnings,
            "session_active": self._session_active,
            "iteration": self._iteration,
            "capital_per_pod": round(float(self._capital_per_pod or 0.0), 4),
            "pods": pods,
            "nav_history": nav_history,
            "broker": broker_status,
            "data_quality": data_quality,
        }

    def get_execution_truth(self) -> dict:
        """Summarize the latest PM-to-execution outcome per pod."""
        generated_at = datetime.now(timezone.utc).isoformat()
        pods: list[dict] = []

        for pod_id in POD_IDS:
            runtime = self._pod_runtimes.get(pod_id)
            if runtime is None:
                pods.append({
                    "pod_id": pod_id,
                    "status": "NOT_STARTED",
                    "stage": "session",
                    "reason": "Pod runtime has not started",
                    "pm_summary": "",
                    "active_trade_count": 0,
                    "active_symbols": [],
                    "thesis_gate": {},
                    "data_gate": {},
                    "last_block": {},
                    "last_order_result": {},
                    "execution_feedback": [],
                })
                continue

            ns = runtime._ns
            pm_decision = ns.get("last_pm_decision") or {}
            if not isinstance(pm_decision, dict):
                pm_decision = {}
            trades = pm_decision.get("trades", []) if isinstance(pm_decision, dict) else []
            active_trades = [
                trade for trade in trades
                if isinstance(trade, dict)
                and str(trade.get("action", "HOLD")).upper() != "HOLD"
            ]
            active_symbols = [
                str(trade.get("symbol", "")).upper()
                for trade in active_trades
                if trade.get("symbol")
            ]
            latest_block = ns.get("last_trade_block") or {}
            order_result = ns.get("last_order_result") or {}
            feedback = list(ns.get("execution_feedback") or [])
            thesis_gate = ns.get("thesis_gate_result") or {}
            data_gate = ns.get("last_data_quality_check") or {}

            if not active_trades:
                status = "NO_ACTIVE_TRADE"
                stage = "pm"
                reason = pm_decision.get("action_summary") or "PM did not propose a BUY/SELL trade"
            elif latest_block and (
                not active_symbols
                or str(latest_block.get("symbol", "")).upper() in active_symbols
            ):
                status = "BLOCKED"
                stage = str(latest_block.get("stage") or "runtime_gate")
                reason = str(latest_block.get("reason") or "Runtime gate blocked trade")
            elif order_result:
                status = str(order_result.get("status") or "SUBMITTED").upper()
                stage = str(order_result.get("stage") or "execution")
                reason = str(
                    order_result.get("reason")
                    or order_result.get("rejection_detail")
                    or order_result.get("rejection_reason")
                    or ""
                )
            else:
                status = "PROPOSED"
                stage = "pm"
                reason = "PM proposed a trade; no runtime block or broker result recorded yet"

            pods.append({
                "pod_id": pod_id,
                "status": status,
                "stage": stage,
                "reason": reason,
                "pm_summary": pm_decision.get("action_summary", "") if isinstance(pm_decision, dict) else "",
                "active_trade_count": len(active_trades),
                "active_symbols": active_symbols,
                "thesis_gate": thesis_gate,
                "data_gate": data_gate,
                "last_block": latest_block,
                "last_order_result": order_result,
                "execution_feedback": feedback[:3],
            })

        status = "OK"
        if any(row["status"] in {"BLOCKED", "REJECTED"} for row in pods):
            status = "CHECK"
        elif any(row["status"] in {"PENDING", "PROPOSED"} for row in pods):
            status = "PENDING"

        return {
            "generated_at": generated_at,
            "status": status,
            "pods": pods,
        }

    async def _publish_reconciled_order_update(self, payload: dict) -> None:
        msg = AgentMessage(
            timestamp=datetime.now(timezone.utc),
            sender="execution.reconciler",
            recipient="dashboard",
            topic="execution.order_update",
            payload=payload,
        )
        await self._event_bus.publish(
            "execution.order_update",
            msg,
            publisher_id="execution.reconciler",
        )

    async def reconcile_execution_state(
        self,
        local_orders: list[dict] | None = None,
        cancel_stale_after_s: float = 60.0,
    ) -> dict:
        """Reconcile stale local order state against Alpaca."""
        now = datetime.now(timezone.utc)
        local_orders = local_orders or []
        checked = 0
        updates: list[dict] = []
        errors: list[str] = []

        for wrapper in local_orders:
            order = wrapper.get("data", wrapper) if isinstance(wrapper, dict) else {}
            if not isinstance(order, dict):
                continue
            local_order_id = order.get("local_order_id")
            broker_order_id = order.get("broker_order_id") or order.get("order_id")
            if local_order_id and not order.get("broker_order_id") and broker_order_id == local_order_id:
                continue
            order_id = broker_order_id
            status = str(order.get("status") or "").upper()
            if not order_id or status not in {"PENDING", "PARTIAL"}:
                continue
            if not hasattr(self._alpaca, "get_order_status"):
                continue
            checked += 1
            try:
                broker = await self._alpaca.get_order_status(order_id)
            except Exception as exc:
                errors.append(f"{order_id}: {exc}")
                continue

            broker_status = str(broker.get("status") or "").upper()
            if broker_status in {"FILLED", "PARTIALLY_FILLED", "PARTIAL"}:
                fill_qty = float(broker.get("filled_qty") or 0.0)
                original_qty = float(order.get("qty") or order.get("quantity") or 0.0)
                ui_status = "FILLED" if original_qty <= 0 or fill_qty >= original_qty - 1e-9 else "PARTIAL"
                update = {
                    "pod_id": order.get("pod_id", "unknown"),
                    "symbol": broker.get("symbol") or order.get("symbol", ""),
                    "side": broker.get("side") or order.get("side", ""),
                    "qty": fill_qty or original_qty,
                    "fill_price": broker.get("filled_avg_price") or order.get("fill_price") or 0.0,
                    "status": ui_status,
                    "order_id": order_id,
                    "local_order_id": local_order_id,
                    "broker_order_id": order_id,
                    "stage": "broker_reconcile",
                    "reason": "Broker status reconciled after dashboard pending state",
                }
            elif broker_status in {"REJECTED", "CANCELED", "CANCELLED", "EXPIRED"}:
                update = {
                    "pod_id": order.get("pod_id", "unknown"),
                    "symbol": broker.get("symbol") or order.get("symbol", ""),
                    "side": broker.get("side") or order.get("side", ""),
                    "qty": float(order.get("qty") or order.get("quantity") or 0.0),
                    "fill_price": broker.get("filled_avg_price") or 0.0,
                    "status": "REJECTED",
                    "order_id": order_id,
                    "local_order_id": local_order_id,
                    "broker_order_id": order_id,
                    "stage": "broker_reconcile",
                    "reason": broker.get("reason") or f"Alpaca order status: {broker_status.lower()}",
                }
            else:
                continue

            updates.append(update)
            try:
                await self._publish_reconciled_order_update(update)
            except Exception as exc:
                errors.append(f"publish {order_id}: {exc}")

        try:
            open_orders = await self._alpaca.get_all_open_orders()
        except Exception as exc:
            open_orders = []
            errors.append(f"Open order reconciliation failed: {exc}")

        canceled: list[dict] = []
        for order in open_orders:
            age_s = self._order_age_seconds(order.get("submitted_at"), now)
            if age_s is None or age_s <= cancel_stale_after_s:
                continue
            order_id = order.get("order_id")
            if not order_id:
                continue
            logger.warning(
                "[reconcile] Cancelling stale order %s (%s, %.0fs old)",
                order_id,
                order.get("symbol"),
                age_s,
            )
            ok = await self._alpaca.cancel_order(order_id)
            update = {
                "pod_id": order.get("pod_id", "unknown"),
                "symbol": order.get("symbol", ""),
                "side": order.get("side", ""),
                "qty": float(order.get("qty") or 0.0),
                "fill_price": 0.0,
                "status": "REJECTED",
                "order_id": order_id,
                "broker_order_id": order_id,
                "stage": "broker_reconcile",
                "reason": (
                    f"Stale open broker order canceled after {age_s:.0f}s without fill"
                    if ok else
                    f"Stale open broker order is older than {age_s:.0f}s; cancellation failed"
                ),
            }
            canceled.append(update)
            updates.append(update)
            try:
                await self._publish_reconciled_order_update(update)
            except Exception as exc:
                errors.append(f"publish {order_id}: {exc}")

        return {
            "checked_local_orders": checked,
            "broker_open_orders": open_orders,
            "updates": updates,
            "canceled_stale_orders": canceled,
            "errors": errors,
            "generated_at": now.isoformat(),
        }

    # ── Session memory persistence ────────────────────────────────────────

    _MEMORY_DIR = Path(__file__).parent.parent.parent / "data"
    _MEMORY_JSON = _MEMORY_DIR / "memory.json"
    _MEMORY_MD = _MEMORY_DIR / "memory.md"

    def _compute_execution_quality(self) -> dict[str, dict]:
        """Aggregate fill / slippage stats per pod from PortfolioAccountant fill logs."""
        out: dict[str, dict] = {}
        for pod_id, runtime in self._pod_runtimes.items():
            acct = runtime._ns.get("accountant")
            if not acct:
                continue
            fills = getattr(acct, "_fill_log", []) or []
            with_slip = [f for f in fills if f.get("slippage_bps") is not None]
            slip_vals = [float(f["slippage_bps"]) for f in with_slip]
            out[pod_id] = {
                "total_fills": len(fills),
                "fills_with_slippage_data": len(with_slip),
                "fills_missing_slippage_data": max(0, len(fills) - len(with_slip)),
                "avg_slippage_bps": round(sum(slip_vals) / len(slip_vals), 2) if slip_vals else None,
                "max_slippage_bps": max(slip_vals) if slip_vals else None,
            }
        return out

    def compute_nav_correlation(self, limit: int = 100) -> dict:
        """Pairwise Pearson correlation of per-pod NAV returns from NavStore."""
        if not self._nav_store:
            return {"ids": [], "matrix": {}, "high_correlation_pairs": []}
        raw = self._nav_store.read_history(pod_id=None, limit=limit * 20)
        from collections import defaultdict

        by_ts: dict[str, dict[str, float]] = defaultdict(dict)
        for r in raw:
            by_ts[r["ts"]][r["pod_id"]] = float(r["nav"])
        ts_sorted = sorted(by_ts.keys())[-limit:]
        if len(ts_sorted) < 3:
            return {"ids": [], "matrix": {}, "high_correlation_pairs": []}
        ids = sorted({p for t in ts_sorted for p in by_ts[t].keys()})
        if len(ids) < 2:
            return {"ids": ids, "matrix": {}, "high_correlation_pairs": []}
        series: dict[str, list[float]] = {pid: [] for pid in ids}
        for t in ts_sorted:
            row = by_ts[t]
            for pid in ids:
                series[pid].append(row.get(pid, 0.0))
        rets: dict[str, list[float]] = {pid: [] for pid in ids}
        for pid in ids:
            navs = series[pid]
            for i in range(1, len(navs)):
                prev = navs[i - 1]
                rets[pid].append((navs[i] - prev) / prev if prev else 0.0)

        def pearson(a: list[float], b: list[float]) -> float:
            n = min(len(a), len(b))
            if n < 2:
                return 0.0
            a, b = a[:n], b[:n]
            sa, sb = sum(a), sum(b)
            sa2 = sum(x * x for x in a)
            sb2 = sum(x * x for x in b)
            sab = sum(a[i] * b[i] for i in range(n))
            den = ((n * sa2 - sa * sa) * (n * sb2 - sb * sb)) ** 0.5
            if den == 0:
                return 0.0
            return (n * sab - sa * sb) / den

        matrix: dict[str, dict[str, float]] = {}
        high: list[dict] = []
        for ia in ids:
            matrix[ia] = {}
            for ib in ids:
                if ia == ib:
                    matrix[ia][ib] = 1.0
                else:
                    v = pearson(rets[ia], rets[ib])
                    matrix[ia][ib] = round(v, 4)
                    if ia < ib and abs(v) > 0.7:
                        high.append({"a": ia, "b": ib, "r": round(v, 4)})
        return {"ids": ids, "matrix": matrix, "high_correlation_pairs": high}

    def _load_memory(self) -> dict | None:
        """Load previous session state from data/memory.json if it exists."""
        if not self._MEMORY_JSON.exists():
            return None
        try:
            raw = self._MEMORY_JSON.read_text(encoding="utf-8")
            data = json.loads(raw)
            logger.info("[session_manager] Loaded memory: %d trades, %d governance decisions",
                        len(data.get("trades", [])), len(data.get("governance", [])))
            return data
        except Exception as e:
            logger.warning("[session_manager] Failed to load memory.json: %s", e)
            return None

    def _save_memory(self) -> None:
        """Persist session state to data/memory.json and data/memory.md."""
        try:
            self._MEMORY_DIR.mkdir(parents=True, exist_ok=True)

            pods_state: dict[str, dict] = {}
            for pod_id, runtime in self._pod_runtimes.items():
                acct = runtime._ns.get("accountant")
                if acct:
                    pods_state[pod_id] = acct.to_state_dict()

            trades: list[dict] = []
            if self._session_logger and hasattr(self._session_logger, "_fill_log"):
                for t in self._session_logger._fill_log:
                    trade = dict(t)
                    for k, v in trade.items():
                        if isinstance(v, datetime):
                            trade[k] = v.isoformat()
                    trades.append(trade)

            # Merge with previously loaded trades to preserve cross-session history
            prev = self._restored_memory or {}
            prev_trades = prev.get("trades", [])
            seen_ids = {t.get("order_id") for t in trades if t.get("order_id")}
            for pt in prev_trades:
                if pt.get("order_id") and pt["order_id"] not in seen_ids:
                    trades.insert(0, pt)
            trades = trades[-200:]  # cap at 200 entries

            governance: list[dict] = []
            for g in getattr(self, "_governance_decisions", []):
                entry = dict(g) if isinstance(g, dict) else {}
                for k, v in entry.items():
                    if isinstance(v, datetime):
                        entry[k] = v.isoformat()
                governance.append(entry)

            # Merge with previously loaded governance to preserve cross-session history
            prev_gov = prev.get("governance", [])
            seen_ts = {g.get("ts") for g in governance if g.get("ts")}
            for pg in prev_gov:
                if pg.get("ts") and pg["ts"] not in seen_ts:
                    governance.insert(0, pg)
            governance = governance[-50:]

            total_nav = sum(ps.get("nav", 0) for ps in pods_state.values())
            total_capital = sum(ps.get("starting_capital", 0) for ps in pods_state.values())

            total_realized = sum(float(ps.get("realized_pnl", 0) or 0) for ps in pods_state.values())
            delta_r = total_realized - self._last_total_realized_snapshot
            self._firm_inception_pnl += delta_r
            self._last_total_realized_snapshot = total_realized
            self._firm_peak_nav = max(self._firm_peak_nav, total_nav)

            exec_quality = self._compute_execution_quality()

            ts_snap = datetime.now(timezone.utc).isoformat()
            if self._nav_store:
                for pod_id, ps in pods_state.items():
                    nav_v = float(ps.get("nav", 0))
                    cash_v = float(ps.get("cash", 0))
                    realized_v = float(ps.get("realized_pnl", 0))
                    invested_v = max(0.0, nav_v - cash_v)
                    try:
                        self._nav_store.write_snapshot(
                            pod_id, nav_v, cash_v, invested_v, realized_v, ts=ts_snap,
                        )
                    except Exception as e:
                        logger.debug("[session_manager] nav snapshot: %s", e)

            closed_trades_state: dict[str, list] = {}
            prev_closed = prev.get("closed_trades_state", {})
            for pod_id, runtime in self._pod_runtimes.items():
                acct = runtime._ns.get("accountant")
                current_closed: list[dict] = []
                if acct:
                    for ct in acct.closed_trades:
                        entry: dict = {}
                        for k, v in ct.items():
                            entry[k] = v.isoformat() if isinstance(v, datetime) else v
                        current_closed.append(entry)
                # Merge with previously saved closed trades to preserve history
                seen_keys = {(c.get("symbol"), c.get("exit_time")) for c in current_closed}
                for pc in prev_closed.get(pod_id, []):
                    if (pc.get("symbol"), pc.get("exit_time")) not in seen_keys:
                        current_closed.append(pc)
                if current_closed:
                    closed_trades_state[pod_id] = current_closed[-100:]

            outcomes_state: dict[str, dict] = {}
            signal_scores_state: dict[str, dict] = {}
            enrichment_state: dict[str, dict] = {}
            for pod_id, runtime in self._pod_runtimes.items():
                tracker = getattr(runtime, "_outcome_tracker", None)
                if tracker and tracker.total_trades > 0:
                    outcomes_state[pod_id] = tracker.to_state_dict()
                scorer = getattr(runtime, "_signal_scorer", None)
                if scorer and scorer.get_hit_rates():
                    signal_scores_state[pod_id] = scorer.to_state_dict()

                # Save research enrichment data per pod
                ns = runtime._ns
                enrich: dict = {}
                for key in ("fred_snapshot", "fred_score", "polymarket_signals",
                            "polymarket_confidence", "macro_score", "poly_sentiment",
                            "social_score"):
                    val = ns.get(key)
                    if val is not None:
                        enrich[key] = val
                # Save x_feed trimmed to 50 items
                x_feed = ns.get("x_feed") or []
                if x_feed:
                    enrich["x_feed"] = x_feed[:50]
                if enrich:
                    enrichment_state[pod_id] = enrich

            # Collect discovered universe per pod (equities only for now)
            discovered_universe: dict = {}
            for pod_id, runtime in self._pod_runtimes.items():
                tickers = runtime._ns.get("discovered_tickers")
                prev_disc = (self._restored_memory or {}).get("discovered_universe", {})
                if tickers:
                    prev_tickers = prev_disc.get(pod_id, {}).get("tickers", {})
                    merged = {**prev_tickers, **tickers}  # current session wins
                    discovered_universe[pod_id] = {
                        "tickers": merged,
                        "last_scan_date": getattr(runtime, "_last_theme_scan_date", None) or "",
                    }
                elif pod_id in prev_disc:
                    # Preserve previous session data if current session has nothing
                    discovered_universe[pod_id] = prev_disc[pod_id]

            memory = {
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "session_start": self._session_start.isoformat() if self._session_start else None,
                "iteration": self._iteration,
                "firm": {
                    "total_nav": round(total_nav, 4),
                    "total_pnl": round(total_nav - total_capital, 4),
                    "initial_capital": round(total_capital, 4),
                    "inception_pnl": round(self._firm_inception_pnl, 4),
                    "peak_nav": round(self._firm_peak_nav, 4),
                },
                "execution_quality": exec_quality,
                "pods": pods_state,
                "trades": trades,
                "governance": governance,
                "enrichment": enrichment_state,
                "trade_outcomes": outcomes_state,
                "signal_scores": signal_scores_state,
                "closed_trades_state": closed_trades_state,
                "discovered_universe": discovered_universe,
                "loss_reviews": {
                    "active": self._loss_reviews,
                    "history": self._loss_review_history[:100],
                },
            }

            self._MEMORY_JSON.write_text(
                json.dumps(memory, indent=2, default=str), encoding="utf-8"
            )

            # Human-readable markdown summary
            md_lines = [
                f"# Session Memory",
                f"",
                f"**Last updated:** {memory['last_updated']}",
                f"**Iteration:** {self._iteration}",
                f"",
                f"## Firm Summary",
                f"",
                f"| Metric | Value |",
                f"|--------|-------|",
                f"| Total NAV | ${total_nav:.2f} |",
                f"| Total P&L | ${total_nav - total_capital:+.2f} |",
                f"| Initial Capital | ${total_capital:.2f} |",
                f"",
                f"## Pod Positions",
                f"",
            ]
            for pod_id, ps in pods_state.items():
                md_lines.append(f"### {pod_id.upper()}")
                md_lines.append(f"")
                md_lines.append(f"NAV: ${ps.get('nav', 0):.2f} | P&L: ${ps.get('daily_pnl', 0):+.2f}")
                md_lines.append(f"")
                positions = ps.get("positions", [])
                if positions:
                    md_lines.append(f"| Symbol | Qty | Avg Entry | Current | Unrl P&L |")
                    md_lines.append(f"|--------|-----|-----------|---------|----------|")
                    for p in positions:
                        curr = p.get("current_price", p["avg_entry"])
                        pnl = p["qty"] * (curr - p["avg_entry"])
                        md_lines.append(
                            f"| {p['symbol']} | {p['qty']:.2f} | ${p['avg_entry']:.2f} "
                            f"| ${curr:.2f} | ${pnl:+.2f} |"
                        )
                else:
                    md_lines.append("_No open positions_")
                md_lines.append("")

            if trades:
                md_lines.append("## Recent Trades (last 20)")
                md_lines.append("")
                md_lines.append("| Time | Pod | Symbol | Side | Qty | Price |")
                md_lines.append("|------|-----|--------|------|-----|-------|")
                for t in trades[-20:]:
                    md_lines.append(
                        f"| {t.get('timestamp', '—')[:19]} | {t.get('pod_id', '—')} "
                        f"| {t.get('symbol', '—')} | {t.get('side', '—')} "
                        f"| {t.get('qty', '—')} | ${t.get('filled_price') or t.get('fill_price') or 0:.2f} |"
                    )
                md_lines.append("")

            self._MEMORY_MD.write_text("\n".join(md_lines), encoding="utf-8")
            logger.debug("[session_manager] Memory saved: %d pods, %d trades", len(pods_state), len(trades))
        except Exception as e:
            logger.warning("[session_manager] Failed to save memory: %s", e)

    async def _hydrate_from_alpaca(self) -> None:
        """Load real positions from Alpaca and inject into pod accountants."""
        try:
            positions = await self._alpaca.get_open_positions()
            if not positions:
                logger.info("[session_manager] Alpaca: no open positions to hydrate")
                # Still run reconcile so pods keep allocated capital.
                cap = self._capital_per_pod or 1000.0
                for pod_id, rt in self._pod_runtimes.items():
                    acct = rt._ns.get("accountant")
                    if acct:
                        acct.reconcile_capital_from_positions(allocated_capital=cap)
                return

            account = await self._alpaca.fetch_account()
            logger.info("[session_manager] Hydrating from Alpaca: %d positions, equity=$%.2f",
                        len(positions), account.get("equity", 0))

            pod_universes: dict[str, set[str]] = {}
            pod_universe_aliases: dict[str, set[str]] = {}
            for pod_id in self._pod_runtimes:
                ns = self._pod_runtimes[pod_id]._ns
                universe = ns.get("universe") or POD_UNIVERSES.get(pod_id, [])
                pod_universes[pod_id] = set(universe)
                aliases: set[str] = set()
                for universe_symbol in universe:
                    aliases.update(symbol_aliases(universe_symbol))
                pod_universe_aliases[pod_id] = aliases

            # Fetch earliest buy dates from Alpaca order history
            earliest_dates: dict[str, str] = {}
            try:
                earliest_dates = await self._alpaca.get_earliest_buy_dates()
            except Exception:
                logger.warning("[session_manager] Could not fetch order history for entry dates")

            for symbol, pos_data in positions.items():
                target_pod = None
                display_symbol = canonical_crypto_symbol(symbol) if is_crypto_symbol(symbol) else symbol
                broker_aliases = symbol_aliases(symbol)
                for pod_id, universe in pod_universes.items():
                    if broker_aliases & pod_universe_aliases.get(pod_id, set()):
                        target_pod = pod_id
                        for universe_symbol in universe:
                            if broker_aliases & symbol_aliases(universe_symbol):
                                display_symbol = universe_symbol
                                break
                        break
                if target_pod is None:
                    for pod_id in self._pod_runtimes:
                        target_pod = pod_id
                        break

                if target_pod and target_pod in self._pod_runtimes:
                    acct = self._pod_runtimes[target_pod]._ns.get("accountant")
                    if acct:
                        acct.load_positions([{
                            "symbol": display_symbol,
                            "qty": pos_data["qty"],
                            "avg_entry": pos_data["entry_price"],
                            "current_price": pos_data["current_price"],
                            "price_source": "alpaca",
                        }])

                        # Set entry date from Alpaca order history (backfill from memory may override)
                        earliest_key = next((a for a in symbol_aliases(display_symbol) if a in earliest_dates), symbol)
                        if earliest_key in earliest_dates and not acct._entry_dates.get(display_symbol):
                            raw_ts = earliest_dates[earliest_key]
                            date_str = raw_ts[:10] if len(raw_ts) >= 10 else raw_ts
                            acct._entry_dates[display_symbol] = date_str
                            logger.debug("[session_manager] Set entry date for %s from order history: %s", display_symbol, date_str)

                        # Ensure held symbols are in the pod universe so bars are fetched
                        ns = self._pod_runtimes[target_pod]._ns
                        current_universe = ns.get("universe") or list(POD_UNIVERSES.get(target_pod, []))
                        if display_symbol not in current_universe:
                            current_universe.append(display_symbol)
                            ns.set("universe", current_universe)
                            logger.info("[session_manager] Added %s to %s universe (held position)", display_symbol, target_pod)
                        logger.info("[session_manager] Hydrated %s: %s %.2f @ $%.2f -> pod %s",
                                    display_symbol, "LONG" if pos_data["qty"] > 0 else "SHORT",
                                    abs(pos_data["qty"]), pos_data["entry_price"], target_pod)

            # Reconcile starting_capital so NAV = invested + cash (fixes invested >> NAV mismatch)
            cap = self._capital_per_pod or 1000.0
            for pod_id, rt in self._pod_runtimes.items():
                acct = rt._ns.get("accountant")
                if acct:
                    acct.reconcile_capital_from_positions(allocated_capital=cap)
        except Exception as e:
            logger.warning("[session_manager] Alpaca hydration failed (non-fatal): %s", e)

    def _backfill_entry_metadata_from_memory(self, memory: dict) -> None:
        """Populate entry dates/theses for hydrated positions using memory.json trades.

        When positions are loaded from Alpaca, the accountant knows qty and cost
        but may have no entry_date, entry_thesis, or fill-level reasoning. This
        method scans the saved trade log for all BUY fills on each currently
        held symbol so the dashboard can audit both the original entry and later
        expansions.
        """
        trades = memory.get("trades", [])
        if not trades:
            return

        backfilled = 0
        for pod_id, rt in self._pod_runtimes.items():
            acct = rt._ns.get("accountant")
            if not acct:
                continue

            held_symbols = set(acct._positions.keys())
            if not held_symbols:
                continue

            for sym in held_symbols:
                pod_buys = [
                    t for t in trades
                    if t.get("pod_id") == pod_id
                    and t.get("symbol") == sym
                    and (t.get("side") or "").lower() == "buy"
                    and t.get("timestamp")
                ]
                if not pod_buys:
                    continue

                pod_buys.sort(key=lambda t: t["timestamp"])
                earliest = pod_buys[0]
                ts = earliest["timestamp"]
                reasoning = self._extract_trade_reasoning(
                    earliest.get("entry_thesis") or earliest.get("reasoning") or "",
                    sym,
                )

                if not acct._entry_dates.get(sym):
                    acct._entry_dates[sym] = ts[:10]
                if reasoning and not acct._entry_theses.get(sym):
                    acct._entry_theses[sym] = reasoning
                if sym not in acct._entry_metadata:
                    acct._entry_metadata[sym] = {
                        "entry_price": acct._cost_basis.get(sym, 0),
                        "entry_time": ts,
                        "entry_thesis": reasoning,
                        "reasoning": reasoning,
                        "conviction": earliest.get("conviction", 0.5),
                        "strategy_tag": earliest.get("strategy_tag", ""),
                        "signal_snapshot": earliest.get("signal_snapshot", {}),
                        "stop_loss_pct": 0.05,
                        "take_profit_pct": 0.15,
                        "exit_when": "",
                        "max_hold_days": 0,
                    }
                else:
                    acct._entry_metadata[sym].setdefault("entry_time", ts)
                    acct._entry_metadata[sym].setdefault("entry_thesis", reasoning)
                    if reasoning and not acct._entry_metadata[sym].get("reasoning"):
                        acct._entry_metadata[sym]["reasoning"] = reasoning

                existing_keys = set()
                for f in getattr(acct, "_fill_log", []):
                    if f.get("symbol") != sym:
                        continue
                    f_ts = f.get("timestamp") or f.get("filled_at") or ""
                    if hasattr(f_ts, "isoformat"):
                        f_ts = f_ts.isoformat()
                    existing_keys.add((str(f.get("order_id", "")), str(f_ts), float(abs(f.get("qty", 0) or 0))))

                for buy in pod_buys:
                    buy_ts = buy.get("timestamp", "")
                    buy_qty = float(abs(buy.get("qty", 0) or 0))
                    order_id = str(buy.get("order_id", ""))
                    key = (order_id, str(buy_ts), buy_qty)
                    if key in existing_keys:
                        continue
                    fill_reasoning = self._extract_trade_reasoning(
                        buy.get("entry_thesis") or buy.get("reasoning") or "",
                        sym,
                    )
                    acct._fill_log.append({
                        "timestamp": buy_ts,
                        "order_id": order_id,
                        "symbol": sym,
                        "qty": buy_qty,
                        "fill_price": (
                            buy.get("filled_price")
                            or buy.get("fill_price")
                            or buy.get("price")
                            or acct._cost_basis.get(sym, 0)
                        ),
                        "side": "BUY",
                        "entry_thesis": fill_reasoning,
                        "reasoning": fill_reasoning,
                        "conviction": buy.get("conviction", 0),
                        "strategy_tag": buy.get("strategy_tag", ""),
                        "signal_snapshot": buy.get("signal_snapshot", {}),
                    })
                    existing_keys.add(key)
                    backfilled += 1
                logger.info(
                    "[session_manager] Backfilled %d buy fill(s) for %s/%s: entry=%s",
                    len(pod_buys), pod_id, sym, ts[:10],
                )

        if backfilled:
            logger.info("[session_manager] Backfilled %d fill records from memory", backfilled)

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

        # Persist final state before shutdown
        self._save_memory()

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
        if self._nav_store:
            try:
                self._nav_store.close()
                logger.info("[session_manager] NavStore closed")
            except Exception as e:
                logger.warning("[session_manager] Error closing NavStore: %s", e)
            self._nav_store = None

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

            perf_data, pos_data, sq_data, events_data = self._collect_report_data()

            report_gen = DailyReportGenerator()
            report_html = report_gen.generate(
                session_dir=self._session_logger.session_dir if self._session_logger else "",
                session_start=getattr(self, "_session_start", None),
                session_end=datetime.now(),
                pods_data=pods_data,
                trades=self._session_logger._fill_log if self._session_logger else [],
                governance=getattr(self, "_governance_decisions", []),
                firm_nav=sum(p.get("risk_metrics", {}).get("nav", 0) for p in pods_data.values()),
                initial_capital=sum(p.get("risk_metrics", {}).get("starting_capital", 0) for p in pods_data.values()),
                performance_data=perf_data,
                positions_data=pos_data,
                signal_quality_data=sq_data,
                upcoming_events=events_data,
            )

            session_dir = self._session_logger.session_dir if self._session_logger else None
            if session_dir:
                report_gen.generate_markdown(
                    session_dir=session_dir,
                    pods_data=pods_data,
                    trades=self._session_logger._fill_log if self._session_logger else [],
                    firm_nav=sum(p.get("risk_metrics", {}).get("nav", 0) for p in pods_data.values()),
                    initial_capital=sum(p.get("risk_metrics", {}).get("starting_capital", 0) for p in pods_data.values()),
                    performance_data=perf_data,
                    positions_data=pos_data,
                    signal_quality_data=sq_data,
                )
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

    def get_all_closed_trades(self) -> list[dict]:
        """Collect closed trades from all pod accountants, sorted by exit time descending."""
        def _date_only(ts) -> str:
            if not ts:
                return ""
            if isinstance(ts, datetime):
                return ts.date().isoformat()
            return str(ts).split("T", 1)[0][:10]

        all_trades = []
        for pod_id, rt in self._pod_runtimes.items():
            acct = rt._ns.get("accountant")
            if not acct:
                continue
            for ct in acct.closed_trades:
                entry_time = ct.get("entry_time", "")
                exit_time = ct.get("exit_time", "")
                holding_days = 0
                if entry_time and exit_time:
                    try:
                        e_d = datetime.fromisoformat(entry_time.split("T")[0]).date()
                        x_d = datetime.fromisoformat(exit_time.split("T")[0]).date()
                        holding_days = (x_d - e_d).days
                    except Exception:
                        pass
                all_trades.append({
                    "pod_id": pod_id,
                    "symbol": ct.get("symbol", ""),
                    "side": ct.get("side", "long"),
                    "entry_price": round(ct.get("entry_price", 0), 2),
                    "exit_price": round(ct.get("exit_price", 0), 2),
                    "qty": round(ct.get("qty", 0), 4),
                    "realized_pnl": round(ct.get("realized_pnl", 0), 4),
                    "entry_time": entry_time,
                    "exit_time": exit_time,
                    "entry_date": _date_only(entry_time),
                    "exit_date": _date_only(exit_time),
                    "holding_days": holding_days,
                    "entry_thesis": ct.get("entry_thesis") or ct.get("entry_reasoning") or "",
                    "entry_reasoning": ct.get("entry_reasoning") or "",
                    "exit_reasoning": ct.get("exit_reasoning") or "",
                    "conviction": ct.get("conviction", 0),
                    "strategy_tag": ct.get("strategy_tag", ""),
                })

        # Also include closed trades from restored memory (proper persisted data)
        prev = self._restored_memory or {}
        existing_keys = {(t["symbol"], t.get("exit_time", "")) for t in all_trades}

        saved_closed = prev.get("closed_trades_state", {})
        if saved_closed:
            for pod_id, pod_trades in saved_closed.items():
                for ct in pod_trades:
                    key = (ct.get("symbol", ""), ct.get("exit_time", ""))
                    if key in existing_keys:
                        continue
                    existing_keys.add(key)
                    entry_time = ct.get("entry_time", "")
                    exit_time = ct.get("exit_time", "")
                    holding_days = 0
                    if entry_time and exit_time:
                        try:
                            e_d = datetime.fromisoformat(entry_time.split("T")[0]).date()
                            x_d = datetime.fromisoformat(exit_time.split("T")[0]).date()
                            holding_days = (x_d - e_d).days
                        except Exception:
                            pass
                    all_trades.append({
                        "pod_id": pod_id,
                        "symbol": ct.get("symbol", ""),
                        "side": ct.get("side", "long"),
                        "entry_price": round(ct.get("entry_price", 0), 2),
                        "exit_price": round(ct.get("exit_price", 0), 2),
                        "qty": round(ct.get("qty", 0), 4),
                        "realized_pnl": round(ct.get("realized_pnl", 0), 4),
                        "entry_time": entry_time,
                        "exit_time": exit_time,
                        "entry_date": _date_only(entry_time),
                        "exit_date": _date_only(exit_time),
                        "holding_days": holding_days,
                        "entry_thesis": ct.get("entry_thesis") or ct.get("entry_reasoning") or "",
                        "entry_reasoning": ct.get("entry_reasoning") or "",
                        "exit_reasoning": ct.get("exit_reasoning") or "",
                        "conviction": ct.get("conviction", 0),
                        "strategy_tag": ct.get("strategy_tag", ""),
                    })
        else:
            # Legacy fallback: reconstruct from trade log SELL fills + matched BUYs
            old_trades = prev.get("trades", [])
            buys_by_key: dict[tuple, list] = {}
            for t in old_trades:
                if (t.get("side") or "").upper() == "BUY":
                    k = (t.get("pod_id", ""), t.get("symbol", ""))
                    buys_by_key.setdefault(k, []).append(t)

            for t in old_trades:
                if (t.get("side") or "").upper() != "SELL":
                    continue
                pod_id = t.get("pod_id", "")
                symbol = t.get("symbol", "")
                exit_time = t.get("timestamp", "")
                dedup_key = (symbol, exit_time)
                if dedup_key in existing_keys:
                    continue
                existing_keys.add(dedup_key)

                exit_price = t.get("fill_price") or t.get("filled_price") or 0
                qty = round(abs(t.get("qty", 0)), 4)

                # Match with the most recent BUY before this SELL
                entry_price = 0.0
                entry_time = ""
                entry_reasoning_raw = ""
                matching_buys = buys_by_key.get((pod_id, symbol), [])
                for b in matching_buys:
                    b_ts = b.get("timestamp", "")
                    if b_ts <= exit_time:
                        entry_price = b.get("fill_price") or b.get("filled_price") or 0
                        entry_time = b.get("timestamp", "")
                        entry_reasoning_raw = b.get("entry_thesis") or b.get("reasoning", "")

                realized_pnl = qty * (exit_price - entry_price) if entry_price > 0 else 0.0
                holding_days = 0
                if entry_time and exit_time:
                    try:
                        e_d = datetime.fromisoformat(entry_time.split("T")[0]).date()
                        x_d = datetime.fromisoformat(exit_time.split("T")[0]).date()
                        holding_days = (x_d - e_d).days
                    except Exception:
                        pass

                # Unwrap JSON-blob reasoning (older sessions stored raw TradeProposal)
                def _unwrap(raw: str, sym: str) -> str:
                    if raw and (raw.startswith('{"trades":') or raw.startswith("{'trades':")):
                        try:
                            proposal = json.loads(raw)
                            for trade in proposal.get("trades", []):
                                if trade.get("symbol") == sym:
                                    return trade.get("reasoning", "")
                        except Exception:
                            pass
                        return ""  # no matching symbol — don't show unrelated reasoning
                    return raw

                all_trades.append({
                    "pod_id": pod_id,
                    "symbol": symbol,
                    "side": "long",
                    "entry_price": round(entry_price, 2),
                    "exit_price": round(exit_price, 2),
                    "qty": qty,
                    "realized_pnl": round(realized_pnl, 4),
                    "entry_time": entry_time,
                    "exit_time": exit_time,
                    "entry_date": _date_only(entry_time),
                    "exit_date": _date_only(exit_time),
                    "holding_days": holding_days,
                    "entry_thesis": _unwrap(entry_reasoning_raw, symbol),
                    "entry_reasoning": _unwrap(entry_reasoning_raw, symbol),
                    "exit_reasoning": _unwrap(t.get("reasoning", ""), symbol),
                    "conviction": t.get("conviction", 0),
                    "strategy_tag": t.get("strategy_tag", ""),
                })

        all_trades.sort(key=lambda x: x.get("exit_time", ""), reverse=True)
        return all_trades

    def get_all_positions(self) -> list[dict]:
        """Get all open positions across all pods, directly from accountants.
        Used by Top Holdings table — bypasses EventBus/WebSocket chain."""
        result = []
        for pod_id, runtime in self._pod_runtimes.items():
            accountant = runtime._ns.get("accountant")
            if not accountant:
                continue
            for symbol, snap in accountant.current_positions.items():
                if snap.qty == 0:
                    continue
                meta = accountant._entry_metadata.get(symbol, {})
                current_notional = snap.qty * snap.current_price
                entry_notional = snap.qty * snap.cost_basis
                result.append({
                    "_pod": pod_id,
                    "symbol": symbol,
                    "qty": snap.qty,
                    "current_price": snap.current_price,
                    "cost_basis": snap.cost_basis,
                    "unrealized_pnl": snap.unrealized_pnl,
                    "notional": current_notional,
                    "current_notional": current_notional,
                    "entry_notional": entry_notional,
                    "notional_basis": "current_price",
                    "entry_date": snap.entry_date or meta.get("entry_time", ""),
                    "entry_thesis": (
                        snap.entry_thesis
                        or meta.get("entry_thesis")
                        or meta.get("reasoning", "")
                    ),
                    "thesis_status": snap.thesis_status or meta.get("thesis_status", "unknown"),
                    "thesis_issues": snap.thesis_issues or meta.get("thesis_issues", []),
                    "thesis_review": snap.thesis_review or meta.get("thesis_review", {}),
                    "price_source": snap.price_source,
                    "price_updated_at": snap.price_updated_at,
                    "price_stale": snap.price_stale,
                })
        return result

    def get_position_detail(self, pod_id: str, symbol: str) -> dict | None:
        """Get full position detail including fill history for a symbol in a pod."""
        runtime = self._pod_runtimes.get(pod_id)
        if not runtime:
            return None
        accountant = runtime._ns.get("accountant")
        if not accountant:
            return None

        snap = accountant.current_positions.get(symbol)
        if not snap:
            return None

        meta = accountant._entry_metadata.get(symbol, {})

        # Compute days held
        days_held = 0
        entry_date_str = snap.entry_date or meta.get("entry_time", "")
        if entry_date_str:
            try:
                from datetime import date as _date
                entry_d = datetime.fromisoformat(entry_date_str.split("T")[0]).date()
                days_held = (_date.today() - entry_d).days
            except Exception:
                pass

        # Gather all fills for this symbol from the accountant fill log
        fills = []
        for f in getattr(accountant, "_fill_log", []):
            if f.get("symbol") != symbol:
                continue
            ts = f.get("timestamp") or f.get("filled_at")
            ts_str = ts.isoformat() if hasattr(ts, "isoformat") else str(ts) if ts else ""
            qty_val = f.get("qty", 0)
            side = (f.get("side") or "").upper()
            if side not in {"BUY", "SELL"}:
                side = "BUY" if qty_val > 0 else "SELL"
            thesis = f.get("entry_thesis") or f.get("reasoning") or ""
            fills.append({
                "timestamp": ts_str,
                "order_id": f.get("order_id", ""),
                "qty": abs(qty_val),
                "fill_price": f.get("fill_price", 0),
                "side": side,
                "entry_thesis": self._extract_trade_reasoning(thesis, symbol),
                "reasoning": self._extract_trade_reasoning(thesis, symbol),
                "conviction": f.get("conviction", 0),
                "strategy_tag": f.get("strategy_tag", ""),
                "signal_snapshot": f.get("signal_snapshot", {}),
                "entry_macro_regime": f.get("entry_macro_regime", ""),
                "thesis_review": f.get("thesis_review", {}),
            })

        # Also include fills from restored memory
        prev = self._restored_memory or {}
        existing_ids = {f2.get("order_id") for f2 in fills if f2.get("order_id")}
        existing_fill_keys = {
            (
                f2.get("timestamp", ""),
                f2.get("side", ""),
                float(f2.get("qty", 0) or 0),
                float(f2.get("fill_price", 0) or 0),
            )
            for f2 in fills
        }
        for t in prev.get("trades", []):
            if t.get("symbol") != symbol or t.get("pod_id") != pod_id:
                continue
            if t.get("order_id") and t["order_id"] in existing_ids:
                continue
            price = t.get("filled_price") or t.get("fill_price", 0)
            mem_key = (
                t.get("timestamp", ""),
                (t.get("side") or "buy").upper(),
                float(abs(t.get("qty", 0) or 0)),
                float(price or 0),
            )
            if mem_key in existing_fill_keys:
                continue
            thesis = t.get("entry_thesis") or t.get("reasoning") or ""
            fills.append({
                "timestamp": t.get("timestamp", ""),
                "order_id": t.get("order_id", ""),
                "qty": abs(t.get("qty", 0)),
                "fill_price": price,
                "side": (t.get("side") or "buy").upper(),
                "entry_thesis": self._extract_trade_reasoning(thesis, symbol),
                "reasoning": self._extract_trade_reasoning(thesis, symbol),
                "conviction": t.get("conviction", 0),
                "strategy_tag": t.get("strategy_tag", ""),
                "signal_snapshot": t.get("signal_snapshot", {}),
                "entry_macro_regime": t.get("entry_macro_regime", ""),
                "thesis_review": t.get("thesis_review", {}),
            })

        fills.sort(key=lambda x: x.get("timestamp", ""))

        # Gather partial exits from closed trades
        partial_exits = []
        total_bought = sum(f["qty"] for f in fills if f["side"] == "BUY") or 1
        for ct in getattr(accountant, "_closed_trades", []):
            if ct.get("symbol") != symbol:
                continue
            qty_sold = ct.get("qty", 0)
            exit_ts = ct.get("exit_time", "")
            partial_exits.append({
                "date": exit_ts[:10] if exit_ts else "",
                "qty_sold": qty_sold,
                "pct_of_original": round(qty_sold / total_bought * 100, 1) if total_bought else 0,
                "exit_price": ct.get("exit_price", 0),
                "realized_pnl": round(ct.get("realized_pnl", 0), 4),
            })

        reasoning_history = accountant.get_reasoning_log(symbol)

        return {
            "symbol": symbol,
            "pod_id": pod_id,
            "qty": snap.qty,
            "cost_basis": snap.cost_basis,
            "current_price": snap.current_price,
            "unrealized_pnl": round(snap.unrealized_pnl, 4),
            "pnl_pct": round(snap.pnl_pct, 2),
            "notional": snap.qty * snap.current_price,
            "current_notional": snap.qty * snap.current_price,
            "entry_notional": snap.qty * snap.cost_basis,
            "notional_basis": "current_price",
            "entry_date": snap.entry_date or meta.get("entry_time", ""),
            "entry_thesis": (
                snap.entry_thesis
                or meta.get("entry_thesis")
                or meta.get("reasoning", "")
            ),
            "stop_loss_pct": meta.get("stop_loss_pct", 0.05),
            "take_profit_pct": meta.get("take_profit_pct", 0.15),
            "max_hold_days": meta.get("max_hold_days", 0),
            "conviction": meta.get("conviction", 0),
            "days_held": days_held,
            "thesis_status": snap.thesis_status or meta.get("thesis_status", "unknown"),
            "thesis_issues": snap.thesis_issues or meta.get("thesis_issues", []),
            "thesis_review": snap.thesis_review or meta.get("thesis_review", {}),
            "price_source": snap.price_source,
            "price_updated_at": snap.price_updated_at,
            "price_stale": snap.price_stale,
            "entry_macro_regime": meta.get("entry_macro_regime", ""),
            "fills": fills,
            "partial_exits": partial_exits,
            "reasoning_history": reasoning_history,
        }

    @staticmethod
    def _extract_trade_reasoning(reasoning: object, symbol: str) -> str:
        """Return human-readable reasoning, unwrapping older raw TradeProposal JSON."""
        text = str(reasoning or "").strip()
        if not text:
            return ""
        if not text.startswith("{"):
            return text
        try:
            proposal = json.loads(text)
        except Exception:
            return text
        trades = proposal.get("trades", []) if isinstance(proposal, dict) else []
        if not isinstance(trades, list):
            return text
        match = None
        for trade in trades:
            if isinstance(trade, dict) and (not symbol or trade.get("symbol") == symbol):
                match = trade
                break
        if match is None and trades and isinstance(trades[0], dict):
            match = trades[0]
        if not match:
            return text
        return str(match.get("entry_thesis") or match.get("reasoning") or match.get("thesis") or text).strip()

    # Context manager support
    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.stop_session()
