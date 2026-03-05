from __future__ import annotations
import asyncio
from src.core.bus.event_bus import EventBus
from src.core.models.pod_summary import PodSummary
from src.core.models.market import Bar, NewsItem
from src.core.models.messages import AgentMessage
from src.core.models.config import PodConfig
from datetime import datetime

class PodGateway:
    """The ONLY I/O boundary for a pod. Serializes all outbound data."""

    def __init__(self, pod_id: str, bus: EventBus, config: PodConfig):
        self._pod_id = pod_id
        self._bus = bus
        self._config = config
        self._mandate_queue: asyncio.Queue = asyncio.Queue()
        self._bar_queues: list[asyncio.Queue] = []
        self._news_queues: list[asyncio.Queue] = []

    async def emit_summary(self, summary: PodSummary) -> None:
        assert summary.pod_id == self._pod_id, "Pod can only emit its own summary"
        clean = PodSummary.model_validate_json(summary.model_dump_json())
        msg = AgentMessage(
            timestamp=datetime.now(),
            sender=f"pod.{self._pod_id}",
            recipient="broadcast",
            topic=f"pod.{self._pod_id}.gateway",
            payload=clean.model_dump(mode="json"),
        )
        await self._bus.publish(f"pod.{self._pod_id}.gateway", msg,
                                publisher_id=f"pod.{self._pod_id}")

    async def receive_mandate(self) -> AgentMessage | None:
        try:
            return self._mandate_queue.get_nowait()
        except asyncio.QueueEmpty:
            return None

    async def subscribe_market_data(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._bar_queues.append(q)
        return q

    async def push_bar(self, bar: Bar) -> None:
        if bar.symbol in self._config.universe:
            for q in self._bar_queues:
                await q.put(bar)

    async def subscribe_news(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._news_queues.append(q)
        return q

    async def push_news(self, item: NewsItem) -> None:
        for q in self._news_queues:
            await q.put(item)
