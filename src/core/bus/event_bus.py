from __future__ import annotations
import asyncio
import re
from collections import defaultdict
from typing import Callable
from ..models.messages import AgentMessage
from .exceptions import TopicAccessError

# Topic ownership rules: (topic_regex, allowed_publisher_regex)
TOPIC_RULES: list[tuple[str, str]] = [
    (r"^pod\.(\w+)\.gateway$", r"^pod\.\1$"),       # pod.X.gateway -> pod.X only
    (r"^governance\.(\w+)$", r"^(ceo|cio|risk_manager)$"),
    (r"^market\.data$", r"^data_feed$"),
    (r"^news\.feed$", r"^news_agent$"),
    (r"^risk\.alert$", r"^risk_manager$"),
    (r"^system\.", r"^system$"),
]

def _check_access(topic: str, publisher_id: str) -> None:
    for topic_pattern, publisher_pattern in TOPIC_RULES:
        m = re.match(topic_pattern, topic)
        if m:
            resolved = re.sub(r"\\(\d+)", lambda x: m.group(int(x.group(1))), publisher_pattern)
            if not re.match(resolved, publisher_id):
                raise TopicAccessError(f"'{publisher_id}' cannot publish to topic '{topic}'")
            return

class EventBus:
    def __init__(self, audit_log=None):
        self._subscribers: dict[str, list[Callable]] = defaultdict(list)
        self._lock = asyncio.Lock()
        self._audit_log = audit_log

    async def publish(self, topic: str, message: AgentMessage, publisher_id: str) -> None:
        _check_access(topic, publisher_id)
        if self._audit_log:
            self._audit_log.record(message)
        handlers = self._subscribers.get(topic, [])
        for handler in handlers:
            if asyncio.iscoroutinefunction(handler):
                asyncio.create_task(handler(message))
            else:
                handler(message)

    async def subscribe(self, topic: str, handler: Callable) -> None:
        async with self._lock:
            self._subscribers[topic].append(handler)

    async def unsubscribe(self, topic: str, handler: Callable) -> None:
        async with self._lock:
            self._subscribers[topic] = [h for h in self._subscribers[topic] if h != handler]
