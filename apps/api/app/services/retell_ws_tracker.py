"""Conexiones activas al Custom LLM WebSocket (diagnóstico voz)."""

from __future__ import annotations

import threading
import time
from typing import Any

_lock = threading.Lock()
_by_call: dict[str, dict[str, Any]] = {}


def mark_ws_connected(call_id: str) -> None:
    """Registra conexión del WebSocket LLM.

    Si `call_id` ya tenía fila (reconexión Retell `auto_reconnect` sobre la
    MISMA llamada — ej. blip de red), preserva `greeting_sent` para que
    `call_details` en la nueva conexión NO repita el saludo a mitad de
    conversación. Solo se resetea si es una fila nueva (primera conexión real).
    """
    cid = (call_id or "").strip()
    if not cid:
        return
    with _lock:
        existing = _by_call.get(cid)
        greeting_already_sent = bool(existing and existing.get("greeting_sent"))
        _by_call[cid] = {
            "call_id": cid,
            "connected_at": time.time(),
            "greeting_sent": greeting_already_sent,
            "reconnected": bool(existing),
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


def has_greeting_been_sent(call_id: str) -> bool:
    """True si esta llamada (por call_id) ya recibió el saludo — incluye
    reconexiones previas. Evita re-saludar a mitad de conversación cuando
    Retell reconecta el WebSocket LLM (`auto_reconnect`)."""
    cid = (call_id or "").strip()
    if not cid:
        return False
    with _lock:
        row = _by_call.get(cid)
        return bool(row and row.get("greeting_sent"))


def mark_ws_disconnected(call_id: str) -> None:
    """Marca desconexión pero NO borra la fila — una reconexión Retell
    (`auto_reconnect`) para el mismo call_id debe poder ver `greeting_sent`
    y otros metadatos previos. `active_ws_calls()` sigue distinguiendo
    llamadas activas via `disconnected_at`."""
    cid = (call_id or "").strip()
    if not cid:
        return
    with _lock:
        row = _by_call.get(cid)
        if row:
            row["disconnected_at"] = time.time()


def set_pending_advanced_topic(call_id: str, topic: str) -> None:
    cid = (call_id or "").strip()
    cleaned = (topic or "").strip()
    if not cid or not cleaned:
        return
    with _lock:
        row = _by_call.setdefault(cid, {"call_id": cid, "connected_at": time.time()})
        row["pending_advanced_topic"] = cleaned


def get_pending_advanced_topic(call_id: str) -> str | None:
    cid = (call_id or "").strip()
    if not cid:
        return None
    with _lock:
        row = _by_call.get(cid)
        if not row:
            return None
        topic = (row.get("pending_advanced_topic") or "").strip()
        return topic or None


def clear_pending_advanced_topic(call_id: str) -> str | None:
    cid = (call_id or "").strip()
    if not cid:
        return None
    with _lock:
        row = _by_call.get(cid)
        if not row:
            return None
        return (row.pop("pending_advanced_topic", None) or "").strip() or None


def mark_script_delivered(call_id: str) -> None:
    cid = (call_id or "").strip()
    if not cid:
        return
    with _lock:
        row = _by_call.setdefault(cid, {"call_id": cid, "connected_at": time.time()})
        row["script_delivered"] = True
        row.pop("pending_advanced_topic", None)


def is_script_delivered(call_id: str) -> bool:
    cid = (call_id or "").strip()
    if not cid:
        return False
    with _lock:
        row = _by_call.get(cid)
        return bool(row and row.get("script_delivered"))


_STALE_DISCONNECTED_TTL_SEC = 600.0


def _prune_stale_locked(now: float) -> None:
    """Purga filas desconectadas hace rato — se conservan solo para la
    ventana de reconexión `auto_reconnect` de Retell, no indefinidamente."""
    stale = [
        cid
        for cid, row in _by_call.items()
        if row.get("disconnected_at") is not None
        and now - float(row["disconnected_at"]) > _STALE_DISCONNECTED_TTL_SEC
    ]
    for cid in stale:
        _by_call.pop(cid, None)


def active_ws_calls() -> list[dict[str, Any]]:
    now = time.time()
    with _lock:
        _prune_stale_locked(now)
        out: list[dict[str, Any]] = []
        for row in _by_call.values():
            item = dict(row)
            item["connected_seconds"] = round(now - float(item.get("connected_at") or now), 1)
            item["is_connected"] = not bool(item.get("disconnected_at"))
            out.append(item)
        return sorted(out, key=lambda r: r.get("connected_at") or 0, reverse=True)
