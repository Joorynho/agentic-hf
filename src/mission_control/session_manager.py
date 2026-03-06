"""Live paper trading session manager — orchestrate pods, governance, and logging."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from src.agents.ceo.ceo_agent import CEOAgent
from src.agents.cio.cio_agent import CIOAgent
from src.agents.governance.governance_orchestrator import GovernanceOrchestrator
from src.agents.risk.cro_agent import CROAgent
from src.backtest.accounting.capital_allocator import CapitalAllocator
from src.core.bus.audit_log import AuditLog
from src.core.bus.event_bus import EventBus
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
from src.pods.templates.beta.researcher import BetaResearcher
from src.pods.templates.beta.signal_agent import BetaSignalAgent
from src.pods.templates.beta.pm_agent import BetaPMAgent
from src.pods.templates.beta.risk_agent import BetaRiskAgent
from src.pods.templates.beta.execution_trader import BetaExecutionTrader
from src.pods.templates.beta.ops_agent import BetaOpsAgent
from src.pods.templates.gamma.researcher import GammaResearcher
from src.pods.templates.gamma.signal_agent import GammaSignalAgent
from src.pods.templates.gamma.pm_agent import GammaPMAgent
from src.pods.templates.gamma.risk_agent import GammaRiskAgent
from src.pods.templates.gamma.execution_trader import GammaExecutionTrader
from src.pods.templates.gamma.ops_agent import GammaOpsAgent
from src.pods.templates.delta.researcher import DeltaResearcher
from src.pods.templates.delta.signal_agent import DeltaSignalAgent
from src.pods.templates.delta.pm_agent import DeltaPMAgent
from src.pods.templates.delta.risk_agent import DeltaRiskAgent
from src.pods.templates.delta.execution_trader import DeltaExecutionTrader
from src.pods.templates.delta.ops_agent import DeltaOpsAgent
from src.pods.templates.epsilon.researcher import EpsilonResearcher
from src.pods.templates.epsilon.signal_agent import EpsilonSignalAgent
from src.pods.templates.epsilon.pm_agent import EpsilonPMAgent
from src.pods.templates.epsilon.risk_agent import EpsilonRiskAgent
from src.pods.templates.epsilon.execution_trader import EpsilonExecutionTrader
from src.pods.templates.epsilon.ops_agent import EpsilonOpsAgent

logger = logging.getLogger(__name__)

POD_IDS = ["alpha", "beta", "gamma", "delta", "epsilon"]

# Pod agent factories keyed by pod_id
POD_AGENTS = {
    "alpha": {
        "researcher": BetaResearcher,  # Reuse Beta agents for Alpha (placeholder)
        "signal": BetaSignalAgent,
        "pm": BetaPMAgent,
        "risk": BetaRiskAgent,
        "exec_trader": BetaExecutionTrader,
        "ops": BetaOpsAgent,
    },
    "beta": {
        "researcher": BetaResearcher,
        "signal": BetaSignalAgent,
        "pm": BetaPMAgent,
        "risk": BetaRiskAgent,
        "exec_trader": BetaExecutionTrader,
        "ops": BetaOpsAgent,
    },
    "gamma": {
        "researcher": GammaResearcher,
        "signal": GammaSignalAgent,
        "pm": GammaPMAgent,
        "risk": GammaRiskAgent,
        "exec_trader": GammaExecutionTrader,
        "ops": GammaOpsAgent,
    },
    "delta": {
        "researcher": DeltaResearcher,
        "signal": DeltaSignalAgent,
        "pm": DeltaPMAgent,
        "risk": DeltaRiskAgent,
        "exec_trader": DeltaExecutionTrader,
        "ops": DeltaOpsAgent,
    },
    "epsilon": {
        "researcher": EpsilonResearcher,
        "signal": EpsilonSignalAgent,
        "pm": EpsilonPMAgent,
        "risk": EpsilonRiskAgent,
        "exec_trader": EpsilonExecutionTrader,
        "ops": EpsilonOpsAgent,
    },
}


class SessionManager:
    """Manage live paper trading session.

    Responsibilities:
    1. Initialize Alpaca adapter and 5 pods with capital
    2. Fetch real-time bars from Alpaca
    3. Push bars to pod runtimes
    4. Run governance loops periodically
    5. Emit pod summaries to EventBus
    6. Log all activity (trades, reasoning, conversations)
    """

    def __init__(
        self,
        alpaca_adapter: Optional[AlpacaAdapter] = None,
        event_bus: Optional[EventBus] = None,
        audit_log: Optional[AuditLog] = None,
        session_dir: Optional[str] = None,
    ):
        """Initialize session manager.

        Args:
            alpaca_adapter: AlpacaAdapter (default creates new instance)
            event_bus: EventBus (default creates new with audit_log)
            audit_log: AuditLog for EventBus (default in-memory)
            session_dir: Directory for logging (default auto-generated)
        """
        self._alpaca = alpaca_adapter or AlpacaAdapter()
        self._audit_log = audit_log or AuditLog()
        self._event_bus = event_bus or EventBus(audit_log=self._audit_log)
        self._session_logger = SessionLogger(session_dir=session_dir)
        self._data_provider = DataProvider(bus=self._event_bus, audit_log=self._audit_log)

        self._pod_gateways: dict[str, PodGateway] = {}
        self._pod_runtimes: dict[str, PodRuntime] = {}
        self._pod_capital: dict[str, float] = {}
        self._governance: Optional[GovernanceOrchestrator] = None
        self._allocator: Optional[CapitalAllocator] = None

        self._session_active = False
        self._capital_per_pod = 0.0
        self._iteration = 0

        logger.info("[session_manager] Initialized with DataProvider")

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
            initial_symbols = ["AAPL", "MSFT", "GOOGL", "TSLA", "AMZN"]

        self._start_time = datetime.now()
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
                pod_config = PodConfig(
                    pod_id=pod_id,
                    name=f"{pod_id.capitalize()} Strategy",
                    strategy_family="multi-signal",
                    universe=initial_symbols,
                    time_horizon=TimeHorizon.INTRADAY,
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

                # Create PodGateway (I/O boundary)
                gateway = PodGateway(pod_id, self._event_bus, pod_config)

                # Create PodRuntime
                runtime = PodRuntime(pod_id=pod_id, namespace=namespace, gateway=gateway, bus=self._event_bus)

                # Instantiate the 6 pod agents using pod-specific factories
                agent_classes = POD_AGENTS[pod_id]
                researcher = agent_classes["researcher"](
                    agent_id=f"{pod_id}.researcher", pod_id=pod_id, namespace=namespace, bus=self._event_bus
                )
                signal = agent_classes["signal"](
                    agent_id=f"{pod_id}.signal", pod_id=pod_id, namespace=namespace, bus=self._event_bus
                )
                pm = agent_classes["pm"](
                    agent_id=f"{pod_id}.pm", pod_id=pod_id, namespace=namespace, bus=self._event_bus
                )
                risk = agent_classes["risk"](
                    agent_id=f"{pod_id}.risk", pod_id=pod_id, namespace=namespace, bus=self._event_bus
                )
                exec_trader = agent_classes["exec_trader"](
                    agent_id=f"{pod_id}.exec_trader", pod_id=pod_id, namespace=namespace, bus=self._event_bus
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

            # Fetch initial market snapshot
            bars = await self._alpaca.fetch_bars(initial_symbols)
            logger.info("[session_manager] Fetched initial bars for %d symbols", len(bars))

            self._session_active = True
            logger.info("[session_manager] Session started: %d pods × $%.2f = $%.2f total capital",
                       len(POD_IDS), capital_per_pod, total_capital)

        except Exception as exc:
            logger.error("[session_manager] Failed to start session: %s", exc)
            raise

    async def run_event_loop(
        self,
        interval_seconds: float = 60.0,
        governance_freq: int = 5,  # Run governance every N iterations
    ) -> None:
        """Run the main event loop.

        Fetches bars, pushes to pods, runs governance, emits summaries.

        Args:
            interval_seconds: Sleep between iterations (default 60 sec = 1 min)
            governance_freq: Run governance every N iterations (default 5 = every 5 min)
        """
        if not self._session_active:
            raise RuntimeError("Session not started; call start_live_session() first")

        logger.info(
            "[session_manager] Starting event loop: %.1f sec interval, governance every %d iter",
            interval_seconds,
            governance_freq,
        )

        try:
            symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]  # Trading universe

            while self._session_active:
                self._iteration += 1

                try:
                    # 1. Fetch latest bars from Alpaca
                    try:
                        bars = await self._alpaca.fetch_bars(symbols, timeframe="1Min")
                        logger.debug("[session_manager] [iter %d] Fetched bars for %d symbols", self._iteration, len(bars))
                    except Exception as e:
                        logger.error("[session_manager] [iter %d] Failed to fetch bars: %s", self._iteration, e)
                        await asyncio.sleep(interval_seconds)
                        continue  # Skip this iteration on fetch failure

                    # 2. Push bars to each pod (async)
                    for pod_id, gateway in self._pod_gateways.items():
                        for symbol in bars:
                            for bar in bars[symbol]:
                                try:
                                    await gateway.push_bar(bar)
                                except Exception as e:
                                    logger.warning(
                                        "[session_manager] [iter %d] Failed to push bar to %s: %s",
                                        self._iteration, pod_id, e
                                    )

                    # 3. Collect pod summaries for governance and emission
                    pod_summaries = await self._collect_pod_summaries()
                    logger.debug("[session_manager] [iter %d] Collected %d pod summaries", self._iteration, len(pod_summaries))

                    # 4. Emit pod summaries to EventBus (for TUI and DataProvider)
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

                    # 5. Every N iterations: run governance cycle
                    if self._iteration > 0 and self._iteration % governance_freq == 0:
                        try:
                            logger.info("[session_manager] [iter %d] Running governance cycle", self._iteration)
                            governance_result = await self._governance.run_full_cycle(pod_summaries)

                            # Extract results
                            breached_pods = governance_result.get("breached_pods", [])
                            mandate = governance_result.get("mandate")

                            # Log governance cycle
                            self._session_logger.log_reasoning(
                                "governance",
                                "cycle",
                                f"Iteration {self._iteration}: Breached={breached_pods}, "
                                f"Loop6_Consensus={governance_result.get('loop6_consensus', False)}, "
                                f"Loop7_Consensus={governance_result.get('loop7_consensus', False)}",
                                metadata={
                                    "iteration": self._iteration,
                                    "breached_pods": breached_pods,
                                    "loop6_consensus": governance_result.get("loop6_consensus", False),
                                    "loop7_consensus": governance_result.get("loop7_consensus", False),
                                    "mandate_authorized_by": mandate.authorized_by if mandate else None,
                                }
                            )

                            if breached_pods:
                                logger.warning(
                                    "[session_manager] [iter %d] Risk breach detected in pods: %s",
                                    self._iteration, breached_pods
                                )

                        except Exception as e:
                            logger.error(
                                "[session_manager] [iter %d] Governance cycle failed: %s",
                                self._iteration, e, exc_info=True
                            )

                    # 6. Periodic account logging
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

                    # 7. Sleep
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
            pod_id: ID of the pod (e.g., 'alpha', 'beta')
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

    async def stop_session(self) -> dict:
        """Stop event loop and gracefully shut down all pods.

        Returns:
            Dictionary with session summary: uptime_seconds, iterations, pods_closed, final_capital.
        """
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

        # Close session logger
        try:
            self._session_logger.close()
            logger.info("[session_manager] Session logs saved to: %s", self._session_logger.session_dir)
        except Exception as e:
            logger.error("[session_manager] Error closing session logger: %s", e)

        # Calculate uptime
        uptime_seconds = (datetime.now() - self._start_time).total_seconds() if hasattr(self, '_start_time') else 0

        # Return session summary
        return {
            "uptime_seconds": uptime_seconds,
            "iterations": self._iteration,
            "pods_closed": closed_count,
            "final_capital": self._capital_per_pod * len(self._pod_runtimes),
        }

    @property
    def data_provider(self) -> DataProvider:
        """Access the DataProvider for TUI injection."""
        return self._data_provider

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
