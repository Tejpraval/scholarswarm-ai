"""Small in-process event bus for streaming workflow agent events over SSE."""
from __future__ import annotations

import asyncio
from typing import Any, Dict

_queues: Dict[str, asyncio.Queue] = {}


def register_run_queue(run_id: str, queue: asyncio.Queue) -> None:
    _queues[run_id] = queue


def unregister_run_queue(run_id: str) -> None:
    _queues.pop(run_id, None)


def publish_agent_event(event: Any) -> None:
    queue = _queues.get(event.run_id)
    if queue is None:
        return
    payload = event.model_dump(mode="json") if hasattr(event, "model_dump") else dict(event)
    try:
        queue.put_nowait({"type": "event", "data": payload})
    except asyncio.QueueFull:
        # Persisted event history remains complete; a slow SSE reader can reconnect.
        pass
