"""In-memory live stream manager for resumable agent chat streaming.

Tracks per-chat active runs, latest streamed metadata, and SSE subscribers so
clients can reconnect after refresh and continue receiving events.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any


class LiveChatStreamManager:
    """Manage in-flight chat stream state and fan-out subscribers."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._runs: dict[str, dict[str, Any]] = {}
        self._subscribers: dict[str, list[asyncio.Queue]] = {}

    async def start(self, chat_id: str) -> bool:
        """Start a run for chat_id.

        Returns False if a run is already active for this chat.
        """
        async with self._lock:
            existing = self._runs.get(chat_id)
            if existing and existing.get("status") == "running":
                return False
            self._runs[chat_id] = {
                "status": "running",
                "started_at": time.time(),
                "thinking_steps": [],
                "tool_calls": [],
                "message": "",
                "error": "",
            }
            self._subscribers.setdefault(chat_id, [])
            return True

    async def publish(self, chat_id: str, event: dict[str, Any]) -> None:
        """Update run snapshot and publish event to all subscribers."""
        async with self._lock:
            run = self._runs.get(chat_id)
            if run:
                etype = event.get("type")
                if etype == "thinking":
                    content = event.get("content")
                    if isinstance(content, str) and content:
                        run["thinking_steps"].append(content)
                elif etype == "tool_call":
                    run["tool_calls"].append({
                        "name": event.get("name"),
                        "arguments": event.get("arguments"),
                        "result": event.get("result"),
                    })
                elif etype == "message":
                    run["message"] = event.get("content", "")
                elif etype == "error":
                    run["error"] = event.get("content", "")
            queues = list(self._subscribers.get(chat_id, []))

        for q in queues:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # Drop event for slow subscriber, keep stream alive.
                pass

    async def finish(self, chat_id: str, status: str = "done") -> None:
        async with self._lock:
            run = self._runs.get(chat_id)
            if run:
                run["status"] = status
                run["finished_at"] = time.time()
            queues = list(self._subscribers.get(chat_id, []))
        done_event = {"type": "done"}
        for q in queues:
            try:
                q.put_nowait(done_event)
            except asyncio.QueueFull:
                pass
        asyncio.create_task(self._cleanup_later(chat_id))

    async def _cleanup_later(self, chat_id: str, delay_sec: float = 120.0) -> None:
        await asyncio.sleep(delay_sec)
        async with self._lock:
            run = self._runs.get(chat_id)
            if run and run.get("status") != "running":
                self._runs.pop(chat_id, None)
            # keep subscribers map key if active queues exist
            if not self._subscribers.get(chat_id):
                self._subscribers.pop(chat_id, None)

    async def snapshot(self, chat_id: str) -> dict[str, Any] | None:
        async with self._lock:
            run = self._runs.get(chat_id)
            if not run:
                return None
            return {
                "status": run.get("status"),
                "started_at": run.get("started_at"),
                "thinking_steps": list(run.get("thinking_steps", [])),
                "tool_calls": list(run.get("tool_calls", [])),
                "message": run.get("message", ""),
                "error": run.get("error", ""),
            }

    async def subscribe(self, chat_id: str) -> asyncio.Queue | None:
        async with self._lock:
            run = self._runs.get(chat_id)
            if not run or run.get("status") != "running":
                return None
            q: asyncio.Queue = asyncio.Queue(maxsize=200)
            self._subscribers.setdefault(chat_id, []).append(q)
            return q

    async def unsubscribe(self, chat_id: str, q: asyncio.Queue) -> None:
        async with self._lock:
            queues = self._subscribers.get(chat_id, [])
            if q in queues:
                queues.remove(q)
            if not queues:
                self._subscribers.pop(chat_id, None)


live_chat_streams = LiveChatStreamManager()
