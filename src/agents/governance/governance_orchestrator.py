from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.agents.ceo.ceo_agent import CEOAgent
from src.agents.cio.cio_agent import CIOAgent
from src.agents.risk.cro_agent import CROAgent
from src.core.bus.collaboration_runner import CollaborationRunner
from src.core.models.allocation import MandateUpdate
from src.core.models.collaboration import CollaborationLoop
from src.core.models.messages import AgentMessage
from src.core.models.pod_summary import PodSummary
from src.mission_control.session_logger import SessionLogger

logger = logging.getLogger(__name__)


class GovernanceOrchestrator:
    """Coordinates firm-level governance loops (Loops 4-7).

    Loop 4: CIO <-> Pod PM negotiation  (max 5 iter)
    Loop 5: CRO <-> Pod Risk interrogation (max 5 iter)
    Loop 6: CEO <-> CIO <-> CRO deliberation (max 5 iter)
    Loop 7: CEO <-> CIO strategy co-decision + CRO validation (max 10 iter)

    Pod agents participate via their governance channel (sanitised PodSummary only --
    isolation is preserved).
    """

    def __init__(
        self,
        ceo: CEOAgent,
        cio: CIOAgent,
        cro: CROAgent,
        runner: CollaborationRunner | None = None,
        session_logger: SessionLogger | None = None,
    ) -> None:
        self._ceo = ceo
        self._cio = cio
        self._cro = cro
        self._session_logger = session_logger
        self._runner = runner or CollaborationRunner(session_logger=session_logger)

    # ------------------------------------------------------------------
    # Loop 6: CEO <-> CIO <-> CRO firm deliberation
    # ------------------------------------------------------------------

    async def run_firm_deliberation(
        self,
        pod_summaries: list[PodSummary],
        trigger: str = "scheduled",
    ) -> CollaborationLoop:
        """Loop 6 -- CEO, CIO, and CRO align on firm posture."""
        logger.info("[governance] Loop 6: firm deliberation triggered by '%s'", trigger)

        items = pod_summaries.values() if isinstance(pod_summaries, dict) else pod_summaries
        initial = AgentMessage(
            timestamp=datetime.now(timezone.utc),
            sender=self._ceo.agent_id,
            recipient="all",
            topic="governance.deliberation",
            payload={
                "action": "ceo_strategy",
                "trigger": trigger,
                "pod_count": len(list(items)),
                "active_pods": [s.pod_id for s in (pod_summaries.values() if isinstance(pod_summaries, dict) else pod_summaries) if s.status.value == "active"],
                "summary": f"Governance deliberation triggered by {trigger}. Reviewing firm posture across all pods.",
            },
        )
        loop = await self._runner.run_loop(
            topic="firm_deliberation",
            participants=[self._ceo, self._cio, self._cro],
            max_iterations=5,
            initial_message=initial,
        )
        logger.info(
            "[governance] Loop 6 complete: consensus=%s iters=%d",
            loop.consensus_reached, loop.iterations_used,
        )
        return loop

    # ------------------------------------------------------------------
    # Loop 7: CEO <-> CIO strategy co-decision (CRO validates)
    # ------------------------------------------------------------------

    async def run_strategy_co_decision(
        self,
        pod_summaries: list[PodSummary],
        proposed_allocations: dict[str, float] | None = None,
    ) -> tuple[CollaborationLoop, MandateUpdate]:
        """Loop 7 -- CEO and CIO co-decide strategy; CRO validates risk constraints."""
        logger.info("[governance] Loop 7: strategy co-decision")

        initial = AgentMessage(
            timestamp=datetime.now(timezone.utc),
            sender=self._ceo.agent_id,
            recipient=self._cio.agent_id,
            topic="governance.strategy",
            payload={
                "action": "cio_proposal",
                "proposed_allocations": proposed_allocations or {},
                "summary": f"Strategy review with {len(pod_summaries)} pods. CEO requests CIO allocation proposal.",
            },
        )

        loop = await self._runner.run_loop(
            topic="strategy_co_decision",
            participants=[self._ceo, self._cio, self._cro],
            max_iterations=10,
            initial_message=initial,
        )

        cio_input = loop.outcome.get("summary", "") or loop.outcome.get("response", "")
        cro_constraints = loop.outcome if loop.consensus_reached else {}
        mandate = await self._ceo.approve_mandate(pod_summaries, cio_input, cro_constraints)

        logger.info(
            "[governance] Loop 7 complete: consensus=%s mandate=%s",
            loop.consensus_reached, mandate.authorized_by,
        )
        return loop, mandate

    # ------------------------------------------------------------------
    # Loop 5: CRO <-> Pod Risk interrogation
    # ------------------------------------------------------------------

    async def run_risk_interrogation(
        self,
        pod_summaries: list[PodSummary],
    ) -> list[str]:
        """Loop 5 -- CRO checks all pods, interrogates breached pods.

        Includes position data and risk metrics from breached pods in the
        interrogation message so CRO has full context.
        """
        breached = await self._cro.check_all_pods(pod_summaries)

        if breached:
            logger.warning("[governance] Loop 5: CRO found breaches in pods: %s", breached)
            items = pod_summaries.values() if isinstance(pod_summaries, dict) else pod_summaries
            summary_map = {s.pod_id: s for s in items}

            for pod_id in breached:
                pod_summary = summary_map.get(pod_id)
                positions_data = []
                risk_data = {}
                if pod_summary:
                    positions_data = [
                        {"symbol": p.symbol, "qty": p.qty, "notional": p.notional,
                         "unrealized_pnl": p.unrealized_pnl}
                        for p in (pod_summary.positions or [])
                    ]
                    risk_data = {
                        "nav": pod_summary.risk_metrics.nav,
                        "daily_pnl": pod_summary.risk_metrics.daily_pnl,
                        "drawdown": pod_summary.risk_metrics.drawdown_from_hwm,
                        "gross_leverage": pod_summary.risk_metrics.gross_leverage,
                        "var_95": pod_summary.risk_metrics.var_95_1d,
                    }

                initial = AgentMessage(
                    timestamp=datetime.now(timezone.utc),
                    sender=self._cro.agent_id,
                    recipient=f"risk.{pod_id}",
                    topic=f"governance.{pod_id}",
                    payload={
                        "action": "pod_risk_query",
                        "pod_id": pod_id,
                        "reason": "CRO breach interrogation",
                        "positions": positions_data,
                        "risk_metrics": risk_data,
                    },
                )
                await self._runner.run_loop(
                    topic=f"cro_interrogation_{pod_id}",
                    participants=[self._cro],
                    max_iterations=1,
                    initial_message=initial,
                )

        return breached

    # ------------------------------------------------------------------
    # Cross-pod correlation check
    # ------------------------------------------------------------------

    def check_cross_pod_conflicts(
        self,
        pod_summaries: list[PodSummary] | dict[str, PodSummary],
    ) -> list[str]:
        """Scan pods for opposing positions on the same symbol.

        Returns a list of human-readable conflict descriptions.
        """
        items = pod_summaries.values() if isinstance(pod_summaries, dict) else pod_summaries

        symbol_positions: dict[str, list[tuple[str, float]]] = {}
        for s in items:
            for p in (s.positions or []):
                symbol_positions.setdefault(p.symbol, []).append((s.pod_id, p.qty))

        conflicts = []
        for symbol, holders in symbol_positions.items():
            if len(holders) < 2:
                continue
            longs = [(pid, qty) for pid, qty in holders if qty > 0]
            shorts = [(pid, qty) for pid, qty in holders if qty < 0]
            if longs and shorts:
                long_pods = ", ".join(f"{pid}(+{qty:.1f})" for pid, qty in longs)
                short_pods = ", ".join(f"{pid}({qty:.1f})" for pid, qty in shorts)
                conflicts.append(f"{symbol}: opposing positions — long [{long_pods}] vs short [{short_pods}]")

        if conflicts:
            logger.info("[governance] Cross-pod conflicts detected: %s", conflicts)
        return conflicts

    # ------------------------------------------------------------------
    # Full governance cycle (Loops 5->6->7 in sequence)
    # ------------------------------------------------------------------

    async def run_full_cycle(
        self,
        pod_summaries: list[PodSummary],
    ) -> dict:
        """Run the complete governance cycle: risk check -> deliberation -> mandate."""
        breached = await self.run_risk_interrogation(pod_summaries)

        cross_pod_conflicts = self.check_cross_pod_conflicts(pod_summaries)

        loop6 = await self.run_firm_deliberation(
            pod_summaries,
            trigger="risk_breach" if breached else "scheduled",
        )

        if loop6.consensus_reached:
            loop7, mandate = await self.run_strategy_co_decision(pod_summaries)
        else:
            loop7 = None
            mandate = await self._ceo.approve_mandate(pod_summaries)

        return {
            "breached_pods": breached,
            "cross_pod_conflicts": cross_pod_conflicts,
            "loop6_consensus": loop6.consensus_reached,
            "loop7_consensus": loop7.consensus_reached if loop7 else False,
            "mandate": mandate,
        }
