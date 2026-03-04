"""In-process event bus for agent SSE notifications.

Uses asyncio.Queue per subscriber for fan-out. Subscribers register for a
specific branch_id and receive events only for that branch.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any


class AgentEventBus:
    """Simple pub/sub for agent events, keyed by branch_id."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue]] = {}

    def subscribe(self, branch_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.setdefault(branch_id, []).append(q)
        return q

    def unsubscribe(self, branch_id: str, q: asyncio.Queue) -> None:
        queues = self._subscribers.get(branch_id, [])
        if q in queues:
            queues.remove(q)
        if not queues:
            self._subscribers.pop(branch_id, None)

    def publish(self, branch_id: str, event: dict[str, Any]) -> None:
        event.setdefault("timestamp", time.time())
        for q in self._subscribers.get(branch_id, []):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def publish_filter_applied(
        self,
        branch_id: str,
        filter_set_ids: list[str],
        matched_count: int,
    ) -> None:
        self.publish(branch_id, {
            "type": "filter-applied",
            "branchId": branch_id,
            "filterSetIds": filter_set_ids,
            "matchedCount": matched_count,
        })


event_bus = AgentEventBus()
