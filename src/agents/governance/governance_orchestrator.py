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

logger = logging.getLogger(__name__)


class GovernanceOrchestrator:
    """Coordinates firm-level governance loops (Loops 4–7).

    Loop 4: CIO ↔ Pod PM negotiation  (max 5 iter)
    Loop 5: CRO ↔ Pod Risk interrogation (max 5 iter)
    Loop 6: CEO ↔ CIO ↔ CRO deliberation (max 5 iter)
    Loop 7: CEO ↔ CIO strategy co-decision + CRO validation (max 10 iter)

    Pod agents participate via their governance channel (sanitised PodSummary only —
    isolation is preserved).
    """

    def __init__(
        self,
        ceo: CEOAgent,
        cio: CIOAgent,
        cro: CROAgent,
        runner: CollaborationRunner | None = None,
    ) -> None:
        self._ceo = ceo
        self._cio = cio
        self._cro = cro
        self._runner = runner or CollaborationRunner()

    # ------------------------------------------------------------------
    # Loop 6: CEO ↔ CIO ↔ CRO firm deliberation
    # ------------------------------------------------------------------

    async def run_firm_deliberation(
        self,
        pod_summaries: list[PodSummary],
        trigger: str = "scheduled",
    ) -> CollaborationLoop:
        """Loop 6 — CEO, CIO, and CRO align on firm posture."""
        logger.info("[governance] Loop 6: firm deliberation triggered by '%s'", trigger)

        initial = AgentMessage(
            timestamp=datetime.now(timezone.utc),
            sender=self._ceo.agent_id,
            recipient="all",
            topic="governance.deliberation",
            payload={
                "action": "ceo_strategy",
                "trigger": trigger,
                "pod_count": len(pod_summaries),
                "active_pods": [s.pod_id for s in pod_summaries if s.status.value == "active"],
            },
        )
        loop = await self._runner.run_loop(
            topic="firm_deliberation",
            participants=[self._cio, self._cro],
            max_iterations=5,
            initial_message=initial,
        )
        logger.info(
            "[governance] Loop 6 complete: consensus=%s iters=%d",
            loop.consensus_reached, loop.iterations_used,
        )
        return loop

    # ------------------------------------------------------------------
    # Loop 7: CEO ↔ CIO strategy co-decision (CRO validates)
    # ------------------------------------------------------------------

    async def run_strategy_co_decision(
        self,
        pod_summaries: list[PodSummary],
        proposed_allocations: dict[str, float] | None = None,
    ) -> tuple[CollaborationLoop, MandateUpdate]:
        """Loop 7 — CEO and CIO co-decide strategy; CRO validates risk constraints."""
        logger.info("[governance] Loop 7: strategy co-decision")

        initial = AgentMessage(
            timestamp=datetime.now(timezone.utc),
            sender=self._ceo.agent_id,
            recipient=self._cio.agent_id,
            topic="governance.strategy",
            payload={
                "action": "cio_proposal",
                "proposed_allocations": proposed_allocations or {},
                "summary": f"Strategy review with {len(pod_summaries)} pods",
            },
        )

        # Phase 1: CEO ↔ CIO (max 10 iter)
        loop = await self._runner.run_loop(
            topic="strategy_co_decision",
            participants=[self._cio, self._cro],
            max_iterations=10,
            initial_message=initial,
        )

        # Phase 2: CEO approves final mandate incorporating loop outcome
        cio_input = loop.outcome.get("summary", "")
        cro_constraints = loop.outcome if loop.consensus_reached else {}
        mandate = await self._ceo.approve_mandate(pod_summaries, cio_input, cro_constraints)

        logger.info(
            "[governance] Loop 7 complete: consensus=%s mandate=%s",
            loop.consensus_reached, mandate.authorized_by,
        )
        return loop, mandate

    # ------------------------------------------------------------------
    # Loop 5: CRO ↔ Pod Risk interrogation
    # ------------------------------------------------------------------

    async def run_risk_interrogation(
        self,
        pod_summaries: list[PodSummary],
    ) -> list[str]:
        """Loop 5 — CRO checks all pods, interrogates breached pods."""
        breached = await self._cro.check_all_pods(pod_summaries)

        if breached:
            logger.warning("[governance] Loop 5: CRO found breaches in pods: %s", breached)
            # CRO requests breakdown from each breached pod (via governance channel)
            for pod_id in breached:
                initial = AgentMessage(
                    timestamp=datetime.now(timezone.utc),
                    sender=self._cro.agent_id,
                    recipient=f"risk.{pod_id}",
                    topic=f"governance.{pod_id}",
                    payload={
                        "action": "pod_risk_query",
                        "pod_id": pod_id,
                        "reason": "CRO breach interrogation",
                    },
                )
                # Single exchange — pod responds, CRO acknowledges (max 5 iter)
                await self._runner.run_loop(
                    topic=f"cro_interrogation_{pod_id}",
                    participants=[self._cro],  # CRO alone — pod not in process (isolation)
                    max_iterations=1,
                    initial_message=initial,
                )

        return breached

    # ------------------------------------------------------------------
    # Full governance cycle (Loops 5→6→7 in sequence)
    # ------------------------------------------------------------------

    async def run_full_cycle(
        self,
        pod_summaries: list[PodSummary],
    ) -> dict:
        """Run the complete governance cycle: risk check → deliberation → mandate."""
        # Loop 5: risk interrogation
        breached = await self.run_risk_interrogation(pod_summaries)

        # Loop 6: firm deliberation
        loop6 = await self.run_firm_deliberation(
            pod_summaries,
            trigger="risk_breach" if breached else "scheduled",
        )

        # Loop 7: strategy + mandate (only if Loop 6 reached consensus)
        if loop6.consensus_reached:
            loop7, mandate = await self.run_strategy_co_decision(pod_summaries)
        else:
            loop7 = None
            mandate = await self._ceo.approve_mandate(pod_summaries)

        return {
            "breached_pods": breached,
            "loop6_consensus": loop6.consensus_reached,
            "loop7_consensus": loop7.consensus_reached if loop7 else False,
            "mandate": mandate,
        }
