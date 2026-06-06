"""Bus in-memory de eventos HUD por usuario (SSE paneles)."""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from typing import Any, AsyncIterator

_queues: dict[str, list[asyncio.Queue[str]]] = defaultdict(list)
_lock = asyncio.Lock()


async def subscribe(user_id: str) -> asyncio.Queue[str]:
    q: asyncio.Queue[str] = asyncio.Queue(maxsize=128)
    async with _lock:
        _queues[user_id].append(q)
    return q


async def unsubscribe(user_id: str, q: asyncio.Queue[str]) -> None:
    async with _lock:
        rows = _queues.get(user_id, [])
        if q in rows:
            rows.remove(q)
        if not rows and user_id in _queues:
            del _queues[user_id]


async def publish(user_id: str, event: dict[str, Any]) -> None:
    payload = json.dumps(event, ensure_ascii=False)
    async with _lock:
        targets = list(_queues.get(user_id, []))
    for q in targets:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            pass


async def stream_events(user_id: str) -> AsyncIterator[str]:
    q = await subscribe(user_id)
    try:
        yield json.dumps({"type": "state", "hud": "idle"})
        while True:
            try:
                payload = await asyncio.wait_for(q.get(), timeout=25.0)
                yield payload
            except asyncio.TimeoutError:
                yield json.dumps({"type": "ping"})
    finally:
        await unsubscribe(user_id, q)
