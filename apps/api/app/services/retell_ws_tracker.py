"""Conexiones activas al Custom LLM WebSocket (diagnóstico voz)."""

from __future__ import annotations

import threading
import time
from typing import Any

_lock = threading.Lock()
_by_call: dict[str, dict[str, Any]] = {}


def mark_ws_connected(call_id: str) -> None:
    cid = (call_id or "").strip()
    if not cid:
        return
    with _lock:
        _by_call[cid] = {
            "call_id": cid,
            "connected_at": time.time(),
            "greeting_sent": False,
            "last_interaction": None,
            "interaction_count": 0,
        }


def note_ws_interaction(call_id: str, interaction_type: str) -> None:
    cid = (call_id or "").strip()
    if not cid:
        return
    with _lock:
        row = _by_call.setdefault(
            cid,
            {"call_id": cid, "connected_at": time.time(), "interaction_count": 0},
        )
        row["last_interaction"] = interaction_type
        row["interaction_count"] = int(row.get("interaction_count") or 0) + 1


def mark_greeting_sent(call_id: str) -> None:
    cid = (call_id or "").strip()
    if not cid:
        return
    with _lock:
        row = _by_call.setdefault(cid, {"call_id": cid, "connected_at": time.time()})
        row["greeting_sent"] = True


def mark_ws_disconnected(call_id: str) -> None:
    cid = (call_id or "").strip()
    if not cid:
        return
    with _lock:
        row = _by_call.pop(cid, None)
        if row:
            row["disconnected_at"] = time.time()


def active_ws_calls() -> list[dict[str, Any]]:
    now = time.time()
    with _lock:
        out: list[dict[str, Any]] = []
        for row in _by_call.values():
            item = dict(row)
            item["connected_seconds"] = round(now - float(item.get("connected_at") or now), 1)
            out.append(item)
        return sorted(out, key=lambda r: r.get("connected_at") or 0, reverse=True)
