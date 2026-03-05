from __future__ import annotations
from typing import Any

class PodNamespace:
    """Isolated key-value store for a single pod.
    Keys are internally prefixed — a pod cannot address another pod's keys."""

    def __init__(self, pod_id: str):
        self._pod_id = pod_id
        self._store: dict[str, Any] = {}

    def _key(self, key: str) -> str:
        bare = key.replace(f"{self._pod_id}::", "")
        return f"{self._pod_id}::{bare}"

    def set(self, key: str, value: Any) -> None:
        self._store[self._key(key)] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self._store.get(self._key(key), default)

    def delete(self, key: str) -> None:
        self._store.pop(self._key(key), None)

    def keys(self) -> list[str]:
        prefix = f"{self._pod_id}::"
        return [k[len(prefix):] for k in self._store if k.startswith(prefix)]
