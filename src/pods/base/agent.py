from __future__ import annotations

from abc import ABC, abstractmethod

from src.core.bus.event_bus import EventBus
from src.core.models.messages import AgentMessage
from src.pods.base.namespace import PodNamespace


class BasePodAgent(ABC):
    """Base class for all 6 intra-pod agents.

    Each agent operates within a single pod. It reads/writes state via PodNamespace
    and may publish events on the EventBus (only to its own pod topics).

    Governance agents (CEO/CIO/CRO) communicate through PodGateway — never directly
    to internal pod agents.
    """

    def __init__(
        self,
        agent_id: str,
        pod_id: str,
        namespace: PodNamespace,
        bus: EventBus,
    ) -> None:
        self._agent_id = agent_id
        self._pod_id = pod_id
        self._ns = namespace
        self._bus = bus

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    def agent_id(self) -> str:
        return self._agent_id

    @property
    def pod_id(self) -> str:
        return self._pod_id

    # ------------------------------------------------------------------
    # Core interface
    # ------------------------------------------------------------------

    @abstractmethod
    async def run_cycle(self, context: dict) -> dict:
        """Execute one agent cycle. Reads from namespace, returns output dict."""
        ...

    async def handle_governance_message(self, msg: AgentMessage) -> AgentMessage | None:
        """Handle an inbound governance query from CEO/CIO/CRO.

        Default: echo back an 'unsupported' response. Subclasses override as needed.
        Only the PM and Risk agents typically respond to governance queries.
        """
        return None

    # ------------------------------------------------------------------
    # Namespace helpers (scoped to this pod)
    # ------------------------------------------------------------------

    def store(self, key: str, value: object) -> None:
        self._ns.set(key, value)

    def recall(self, key: str, default: object = None) -> object:
        return self._ns.get(key, default)
