"""Live paper trading session manager — orchestrate pods, governance, and logging."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from src.core.bus.audit_log import AuditLog
from src.core.bus.event_bus import EventBus
from src.core.models.messages import AgentMessage
from src.execution.paper.alpaca_adapter import AlpacaAdapter
from src.mission_control.data_provider import DataProvider
from src.mission_control.session_logger import SessionLogger

logger = logging.getLogger(__name__)

POD_IDS = ["alpha", "beta", "gamma", "delta", "epsilon"]


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

        self._pod_gateways = {}  # TODO: initialize pod gateways
        self._pod_runtimes = {}  # TODO: initialize pod runtimes
        self._governance = None  # TODO: initialize governance orchestrator

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

            # TODO: Initialize pods with capital allocation
            # For each pod_id:
            #   - Create PodNamespace
            #   - Create PodGateway
            #   - Create PodRuntime with 6 agents
            #   - Subscribe to pod summary events

            # TODO: Initialize governance orchestrator
            # - Create CEO, CIO, CRO agents
            # - Wire into GovernanceOrchestrator

            # TODO: Fetch initial market snapshot
            bars = await self._alpaca.fetch_bars(initial_symbols)
            logger.info("[session_manager] Fetched initial bars for %d symbols", len(bars))

            self._session_active = True
            logger.info("[session_manager] Session started")

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
            symbols = ["AAPL", "MSFT", "GOOGL", "TSLA", "AMZN"]  # TODO: get from pod configs

            while self._session_active:
                self._iteration += 1

                try:
                    # 1. Fetch latest bars from Alpaca
                    bars = await self._alpaca.fetch_bars(symbols, timeframe="1Min")
                    logger.debug("[session_manager] [iter %d] Fetched bars", self._iteration)

                    # 2. Push bars to each pod (async)
                    # TODO: for pod_id, gateway in self._pod_gateways.items():
                    #       for symbol in bars:
                    #           for bar in bars[symbol]:
                    #               await gateway.push_bar(bar)

                    # 3. Every N iterations: run governance
                    if self._iteration % governance_freq == 0:
                        logger.info("[session_manager] [iter %d] Running governance cycle", self._iteration)
                        # TODO: await self._governance.run_full_cycle(pod_summaries)

                    # 4. Emit pod summaries to EventBus
                    # TODO: for pod_id, gateway in self._pod_gateways.items():
                    #       summary = await gateway.get_summary()
                    #       await gateway.emit_summary(summary)

                    # 5. Log session state
                    if self._iteration % 10 == 0:
                        account = await self._alpaca.fetch_account()
                        logger.info(
                            "[session_manager] [iter %d] Account: equity=$%.2f, positions=%d",
                            self._iteration,
                            account["equity"],
                            account["position_count"],
                        )

                    # 6. Sleep
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

    async def stop_session(self) -> None:
        """Stop the session and cleanup."""
        logger.info("[session_manager] Stopping session")
        self._session_active = False

        try:
            # TODO: Close all pod positions
            # positions = await self._alpaca.get_open_positions()
            # if positions:
            #     logger.info("[session_manager] Closing %d open positions", len(positions))
            #     await self._alpaca.close_all_positions()

            self._session_logger.close()
            logger.info("[session_manager] Session stopped")

        except Exception as exc:
            logger.error("[session_manager] Error stopping session: %s", exc)

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
