"""Estado de navegación por usuario — GPS, ruta activa y acciones para el cliente."""

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
        "location": None,
        "route": None,
        "place_options": None,
        "place_query": "",
        "client_action": None,
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


def update_location(
    user_id: str,
    *,
    lat: float,
    lng: float,
    heading: float | None = None,
    speed: float | None = None,
    accuracy: float | None = None,
) -> None:
    session = _get(user_id)
    with _lock:
        session["location"] = {
            "lat": lat,
            "lng": lng,
            "heading": heading,
            "speed": speed,
            "accuracy": accuracy,
            "updated_at": _now(),
        }
        session["updated_at"] = _now()


def get_location(user_id: str) -> dict[str, Any] | None:
    loc = _get(user_id).get("location")
    return deepcopy(loc) if loc else None


def set_route(user_id: str, route: dict[str, Any] | None) -> None:
    session = _get(user_id)
    with _lock:
        session["route"] = deepcopy(route) if route else None
        session["updated_at"] = _now()


def get_route(user_id: str) -> dict[str, Any] | None:
    route = _get(user_id).get("route")
    return deepcopy(route) if route else None


def set_place_options(
    user_id: str,
    places: list[dict[str, Any]],
    *,
    query: str = "",
) -> None:
    session = _get(user_id)
    with _lock:
        session["place_options"] = deepcopy(places)
        session["place_query"] = (query or "").strip()
        session["updated_at"] = _now()


def get_place_options(user_id: str) -> list[dict[str, Any]]:
    opts = _get(user_id).get("place_options")
    return deepcopy(opts) if isinstance(opts, list) else []


def clear_place_options(user_id: str) -> None:
    session = _get(user_id)
    with _lock:
        session["place_options"] = None
        session["place_query"] = ""
        session["updated_at"] = _now()


def push_client_action(user_id: str, action: str, payload: dict[str, Any] | None = None) -> None:
    session = _get(user_id)
    with _lock:
        session["client_action"] = {
            "action": action,
            "payload": payload or {},
            "id": int(_now() * 1000),
        }
        session["updated_at"] = _now()


def peek_client_action(user_id: str) -> dict[str, Any] | None:
    action = _get(user_id).get("client_action")
    return deepcopy(action) if action else None


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
            "location": deepcopy(session.get("location")),
            "route": deepcopy(session.get("route")),
            "place_options": deepcopy(session.get("place_options")),
            "place_query": str(session.get("place_query") or ""),
            "client_action": deepcopy(action) if action else None,
            "navigating": bool(session.get("route")),
        }


def clear_navigation(user_id: str) -> None:
    session = _get(user_id)
    with _lock:
        session["route"] = None
        session["place_options"] = None
        session["place_query"] = ""
        session["updated_at"] = _now()
