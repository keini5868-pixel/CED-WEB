"""Instrucciones de navegación habladas por CED (Retell agent_interrupt)."""

from __future__ import annotations

import logging
import threading
from typing import Any

from app.services import navigation_session as nav_session
from app.services import voice_client_session as vcs
from app.services.navigation_maps import _haversine_m

logger = logging.getLogger(__name__)

ANNOUNCE_DISTANCE_M = 300
ADVANCE_STEP_M = 50
ARRIVAL_DISTANCE_M = 50

_lock = threading.Lock()
_pending_speech: dict[str, list[str]] = {}


def enqueue_navigation_speech(user_id: str, text: str) -> None:
    msg = (text or "").strip()
    if not msg:
        return
    uid = user_id.strip()
    with _lock:
        rows = list(_pending_speech.get(uid) or [])
        rows.append(msg)
        _pending_speech[uid] = rows[-8:]
    vcs.push_tool_event(
        uid,
        {
            "type": "navigation_instruction",
            "channel": "navigation_instruction",
            "text": msg,
            "hud_feed": False,
        },
    )
    logger.info("[NAV:VOICE] queued user=%s text=%s", uid[:8], msg[:80])


def pop_navigation_speech(user_id: str) -> str | None:
    uid = user_id.strip()
    with _lock:
        rows = list(_pending_speech.get(uid) or [])
        if not rows:
            return None
        text = rows.pop(0)
        if rows:
            _pending_speech[uid] = rows
        else:
            _pending_speech.pop(uid, None)
        return text


def process_navigation_voice(user_id: str, lat: float, lng: float) -> None:
    if not nav_session.is_navigating(user_id):
        return
    route = nav_session.get_route(user_id)
    if not route:
        return

    dest = route.get("destination") or {}
    dest_lat = dest.get("lat")
    dest_lng = dest.get("lng")
    if dest_lat is not None and dest_lng is not None:
        dest_dist = _haversine_m(lat, lng, float(dest_lat), float(dest_lng))
        if dest_dist < ARRIVAL_DISTANCE_M:
            enqueue_navigation_speech(user_id, "Ha llegado a su destino, señor.")
            nav_session.clear_navigation(user_id)
            nav_session.set_navigating(user_id, False)
            nav_session.push_client_action(user_id, "cancel_navigation", {})
            return

    steps: list[dict[str, Any]] = list(route.get("steps") or [])
    if not steps:
        return

    step_idx = nav_session.get_current_step_index(user_id)
    if step_idx >= len(steps):
        return

    step = steps[step_idx]
    end = step.get("end") or {}
    end_lat = end.get("lat")
    end_lng = end.get("lng")
    if end_lat is None or end_lng is None:
        return

    dist = _haversine_m(lat, lng, float(end_lat), float(end_lng))

    if dist < ADVANCE_STEP_M and step_idx < len(steps) - 1:
        nav_session.set_current_step_index(user_id, step_idx + 1)
        nav_session.clear_step_announced(user_id, step_idx)
        return

    if dist >= ANNOUNCE_DISTANCE_M or nav_session.is_step_announced(user_id, step_idx):
        return

    instruction = str(step.get("instruction") or "Continúe por la ruta").strip()
    meters = int(dist)
    text = (
        f"En {meters} metros, {instruction}"
        if meters > 50
        else instruction
    )
    enqueue_navigation_speech(user_id, text)
    nav_session.mark_step_announced(user_id, step_idx)
