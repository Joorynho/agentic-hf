from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.core.models.collaboration import CollaborationLoop
from src.core.models.messages import AgentMessage
from src.mission_control.session_logger import SessionLogger

logger = logging.getLogger(__name__)


class CollaborationRunner:
    """Runs bounded deliberation loops between agents.

    Each iteration delivers the latest message to every participant (except
    the sender), collects their responses, and checks for consensus.

    Consensus is signalled when a response payload contains {"consensus": True}.
    If max_iterations is reached without consensus, the loop returns a
    "hold / no_consensus" outcome — the caller decides what to do.

    Full transcript is stored in CollaborationLoop.messages for audit.
    """

    def __init__(self, session_logger: SessionLogger | None = None):
        """Initialize CollaborationRunner.

        Args:
            session_logger: Optional SessionLogger for persisting completed loops.
        """
        self._session_logger = session_logger

    async def run_loop(
        self,
        topic: str,
        participants: list,  # list of BasePodAgent or governance agents
        max_iterations: int,
        initial_message: AgentMessage,
    ) -> CollaborationLoop:
        loop = CollaborationLoop(
            topic=topic,
            participants=[p.agent_id for p in participants],
            max_iterations=max_iterations,
            messages=[initial_message],
            started_at=datetime.now(timezone.utc),
        )

        current_message = initial_message

        for iteration in range(max_iterations):
            loop.iterations_used = iteration + 1
            responses: list[AgentMessage] = []

            for agent in participants:
                if agent.agent_id == current_message.sender:
                    continue
                try:
                    response = await agent.handle_governance_message(current_message, history=list(loop.messages))
                except TypeError:
                    response = await agent.handle_governance_message(current_message)
                if response is not None:
                    responses.append(response)
                    loop.messages.append(response)

            if not responses:
                logger.debug("Collaboration loop '%s': no responses at iter %d", topic, iteration)
                break

            # Consensus: all respondents agree
            if all(r.payload.get("consensus") is True for r in responses):
                loop.consensus_reached = True
                loop.outcome = responses[-1].payload.get("outcome", {})
                logger.debug("Collaboration loop '%s': consensus at iter %d", topic, iteration + 1)
                break

            current_message = responses[-1]

        if not loop.consensus_reached:
            loop.outcome = {"action": "hold", "reason": "no_consensus"}
            logger.info(
                "Collaboration loop '%s': no consensus after %d iterations — holding",
                topic,
                loop.iterations_used,
            )

        loop.completed_at = datetime.now(timezone.utc)

        # Log completed loop to session persistence
        if self._session_logger:
            self._session_logger.log_collaboration_loop(loop)

        return loop
