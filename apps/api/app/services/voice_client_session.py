"""Estado cliente voz — cámara, capturas y acciones para Retell (tools server-side)."""

from __future__ import annotations

import threading
import time
from copy import deepcopy
from typing import Any

_lock = threading.Lock()
_sessions: dict[str, dict[str, Any]] = {}
_TTL_SEC = 3600


def _now() -> float:
    return time.time()


def _fresh_session() -> dict[str, Any]:
    return {
        "client_action": None,
        "camera_active": False,
        "camera_updated_at": 0.0,
        "vision_results": {},
        "last_publishable_image": None,
        "updated_at": _now(),
    }


def _get(user_id: str) -> dict[str, Any]:
    uid = user_id.strip()
    if not uid:
        return _fresh_session()
    with _lock:
        session = _sessions.get(uid)
        if not session or _now() - float(session.get("updated_at") or 0) > _TTL_SEC:
            session = _fresh_session()
            _sessions[uid] = session
        return session


def set_camera_active(user_id: str, active: bool) -> None:
    session = _get(user_id)
    with _lock:
        session["camera_active"] = bool(active)
        session["camera_updated_at"] = _now()
        session["updated_at"] = _now()


def is_camera_active(user_id: str, *, max_age_sec: float = 120.0) -> bool:
    session = _get(user_id)
    with _lock:
        if not session.get("camera_active"):
            return False
        age = _now() - float(session.get("camera_updated_at") or 0)
        return age <= max_age_sec


def push_client_action(user_id: str, action: str, payload: dict[str, Any] | None = None) -> int:
    session = _get(user_id)
    action_id = int(_now() * 1000)
    with _lock:
        session["client_action"] = {
            "action": action,
            "payload": payload or {},
            "id": action_id,
        }
        session["updated_at"] = _now()
    return action_id


def consume_client_action(user_id: str, action_id: int | None = None) -> dict[str, Any] | None:
    session = _get(user_id)
    with _lock:
        current = session.get("client_action")
        if not current:
            return None
        if action_id is not None and int(current.get("id") or 0) != int(action_id):
            return None
        session["client_action"] = None
        return deepcopy(current)


def get_state(user_id: str, *, consume_action: bool = False) -> dict[str, Any]:
    session = _get(user_id)
    with _lock:
        action = session.get("client_action")
        if consume_action and action:
            session["client_action"] = None
        return {
            "camera_active": bool(session.get("camera_active")),
            "client_action": deepcopy(action) if action else None,
        }


def set_vision_result(user_id: str, request_id: int, summary: str) -> None:
    session = _get(user_id)
    with _lock:
        results: dict[str, Any] = session.setdefault("vision_results", {})
        results[str(request_id)] = {
            "summary": summary.strip(),
            "at": _now(),
        }
        session["updated_at"] = _now()


def pop_vision_result(user_id: str, request_id: int, *, max_age_sec: float = 30.0) -> str | None:
    session = _get(user_id)
    key = str(request_id)
    with _lock:
        results: dict[str, Any] = session.get("vision_results") or {}
        row = results.pop(key, None)
        session["vision_results"] = results
        if not row:
            return None
        age = _now() - float(row.get("at") or 0)
        if age > max_age_sec:
            return None
        text = str(row.get("summary") or "").strip()
        return text or None


def set_last_publishable_image(
    user_id: str,
    *,
    image_url: str | None = None,
    image_data: str | None = None,
) -> None:
    """Imagen del chat o generada — disponible para publicar_instagram en voz Retell."""
    url = (image_url or "").strip()
    data = (image_data or "").strip()
    if not url and not data:
        return
    session = _get(user_id)
    with _lock:
        session["last_publishable_image"] = {
            "url": url or None,
            "data": data or None,
            "at": _now(),
        }
        session["updated_at"] = _now()


def get_last_publishable_image(user_id: str, *, max_age_sec: float = 900.0) -> dict[str, str] | None:
    session = _get(user_id)
    with _lock:
        row = session.get("last_publishable_image")
        if not row:
            return None
        age = _now() - float(row.get("at") or 0)
        if age > max_age_sec:
            session["last_publishable_image"] = None
            return None
        url = str(row.get("url") or "").strip()
        data = str(row.get("data") or "").strip()
        if not url and not data:
            return None
        out: dict[str, str] = {}
        if url:
            out["url"] = url
        if data:
            out["data"] = data
        return out
