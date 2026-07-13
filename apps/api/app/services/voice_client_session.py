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
        "camera_stream_present": False,
        "camera_permission_granted": False,
        "camera_updated_at": 0.0,
        "vision_results": {},
        "last_publishable_image": None,
        "publishable_images": [],
        "awaiting_instagram_caption": False,
        "active_voice_call_id": None,
        "active_mode": None,
        "map_search_results": [],
        "last_vision_summary": "",
        "tool_events": [],
        "updated_at": _now(),
        "gmail_inbox_cache": [],
        "gmail_awaiting_pick": False,
        "gmail_pending_send": None,
        "finance_pending_write": None,
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


def set_camera_permission_granted(user_id: str, granted: bool) -> None:
    session = _get(user_id)
    with _lock:
        session["camera_permission_granted"] = bool(granted)
        session["updated_at"] = _now()


def is_camera_permission_granted(user_id: str) -> bool:
    return bool(_get(user_id).get("camera_permission_granted"))


def set_camera_active(
    user_id: str,
    active: bool,
    *,
    stream_present: bool | None = None,
) -> None:
    session = _get(user_id)
    with _lock:
        session["camera_active"] = bool(active)
        if stream_present is not None:
            session["camera_stream_present"] = bool(stream_present)
        elif not active:
            session["camera_stream_present"] = False
        session["camera_updated_at"] = _now()
        if active:
            session["active_mode"] = "camera"
        elif session.get("active_mode") == "camera":
            session["active_mode"] = None
        session["updated_at"] = _now()


def set_active_mode(user_id: str, mode: str | None) -> None:
    session = _get(user_id)
    with _lock:
        session["active_mode"] = (mode or "").strip() or None
        session["updated_at"] = _now()


def get_active_mode(user_id: str) -> str | None:
    mode = _get(user_id).get("active_mode")
    return str(mode).strip() if mode else None


def set_map_search_results(user_id: str, places: list[dict[str, Any]] | None) -> None:
    session = _get(user_id)
    with _lock:
        session["map_search_results"] = deepcopy(places or [])
        session["updated_at"] = _now()


def get_map_search_results(user_id: str) -> list[dict[str, Any]]:
    rows = _get(user_id).get("map_search_results")
    return deepcopy(rows) if isinstance(rows, list) else []


def set_last_vision_summary(user_id: str, summary: str) -> None:
    session = _get(user_id)
    with _lock:
        session["last_vision_summary"] = str(summary or "").strip()[:500]
        session["updated_at"] = _now()


def get_last_vision_summary(user_id: str) -> str:
    return str(_get(user_id).get("last_vision_summary") or "").strip()


def get_active_mode_prompt(user_id: str) -> str:
    mode = get_active_mode(user_id)
    if mode == "map":
        count = len(get_map_search_results(user_id))
        options = (
            f"Opciones en pantalla: {count} lugares."
            if count
            else "Sin resultados de búsqueda activos."
        )
        return (
            "# MODO ACTIVO: MAPA/NAVEGACIÓN\n"
            "El usuario está en modo de conducción con el mapa activo.\n"
            f"{options}\n"
            "Comandos disponibles en este modo:\n"
            '- "busca X" → search_nearby_places(X)\n'
            '- "el primero/segundo/más cercano" → start_navigation(index)\n'
            '- "inicia/arranca/dale/sí" → confirmar e iniciar navegación\n'
            '- "¿cuánto falta?" → dar ETA actual\n'
            '- "detener/parar/ya llegué" → stop_navigation()\n'
            "Responde brevemente. El usuario está conduciendo.\n"
            "NO mezcles instrucciones GPS paso a paso en tus respuestas."
        )
    if mode == "camera":
        return (
            "# MODO ACTIVO: CÁMARA\n"
            "El usuario tiene la cámara activa.\n"
            "Analiza automáticamente lo que muestra.\n"
            'Si pregunta "¿qué ves?" → analyze_camera_frame()'
        )
    if mode == "prospect":
        return (
            "# MODO ACTIVO: PROSPECCIÓN\n"
            "El usuario está en modo prospección comercial.\n"
            "Responde con foco en leads, segmentación y seguimiento."
        )
    return ""


def is_camera_active(user_id: str, *, max_age_sec: float = 45.0) -> bool:
    """Cámara activa solo si el cliente reporta stream presente con heartbeat reciente."""
    session = _get(user_id)
    with _lock:
        if not session.get("camera_active"):
            return False
        if not session.get("camera_stream_present"):
            return False
        age = _now() - float(session.get("camera_updated_at") or 0)
        return age <= max_age_sec


def get_camera_status(user_id: str) -> dict[str, bool | float]:
    """Estado de cámara para logs y gates de ACK."""
    session = _get(user_id)
    with _lock:
        return {
            "camera_active": bool(session.get("camera_active")),
            "camera_stream_present": bool(session.get("camera_stream_present")),
            "age_sec": _now() - float(session.get("camera_updated_at") or 0),
        }


def push_tool_event(user_id: str, event: dict[str, Any]) -> int:
    session = _get(user_id)
    event_id = int(_now() * 1000)
    row = {"id": event_id, "at": _now(), **event}
    with _lock:
        events: list[dict[str, Any]] = list(session.get("tool_events") or [])
        events.append(row)
        session["tool_events"] = events[-24:]
        session["updated_at"] = _now()
    return event_id


def consume_tool_events(user_id: str, *, since_id: int = 0) -> list[dict[str, Any]]:
    session = _get(user_id)
    with _lock:
        events: list[dict[str, Any]] = list(session.get("tool_events") or [])
        if since_id <= 0:
            session["tool_events"] = []
            return events
        fresh = [e for e in events if int(e.get("id") or 0) > since_id]
        session["tool_events"] = [e for e in events if int(e.get("id") or 0) <= since_id]
        return fresh


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
            "camera_stream_present": bool(session.get("camera_stream_present")),
            "client_action": deepcopy(action) if action else None,
            "tool_events": deepcopy(session.get("tool_events") or []),
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


def begin_voice_publish_session(user_id: str, voice_call_id: str) -> None:
    """Nueva llamada Retell — descarta imagen solo si cambió el call_id."""
    cid = (voice_call_id or "").strip()
    if not cid:
        return
    session = _get(user_id)
    with _lock:
        prev = str(session.get("active_voice_call_id") or "").strip()
        if prev and prev != cid:
            session["last_publishable_image"] = None
            session["publishable_images"] = []
            session["awaiting_instagram_caption"] = False
        session["active_voice_call_id"] = cid
        row = session.get("last_publishable_image")
        if isinstance(row, dict) and not str(row.get("voice_call_id") or "").strip():
            row["voice_call_id"] = cid
        session["updated_at"] = _now()


def sync_voice_call(user_id: str, voice_call_id: str) -> None:
    """Alinea call_id activo sin borrar imagen ya adjunta en la misma llamada."""
    begin_voice_publish_session(user_id, voice_call_id)


def ensure_active_voice_call(user_id: str) -> str | None:
    """Devuelve call_id activo; recupera del registro Retell si hace falta."""
    uid = (user_id or "").strip()
    if not uid:
        return None
    with _lock:
        session = _sessions.get(uid)
        if session:
            active = str(session.get("active_voice_call_id") or "").strip()
            if active:
                return active
    from app.services.retell_call_registry import resolve_user_active_call

    call_id = resolve_user_active_call(uid)
    if not call_id:
        return None
    begin_voice_publish_session(uid, call_id)
    return call_id


def is_voice_session_active(user_id: str) -> bool:
    return bool(ensure_active_voice_call(user_id))


def clear_last_publishable_image(user_id: str) -> None:
    session = _get(user_id)
    with _lock:
        session["last_publishable_image"] = None
        session["publishable_images"] = []
        session["awaiting_instagram_caption"] = False
        session["updated_at"] = _now()


def end_voice_publish_session(user_id: str, voice_call_id: str | None = None) -> None:
    session = _get(user_id)
    with _lock:
        active = str(session.get("active_voice_call_id") or "").strip()
        end_id = (voice_call_id or "").strip()
        if end_id and active and active != end_id:
            return
        session["active_voice_call_id"] = None
        session["last_publishable_image"] = None
        session["publishable_images"] = []
        session["awaiting_instagram_caption"] = False
        session["updated_at"] = _now()


def _append_publishable_image(
    session: dict[str, Any],
    *,
    url: str,
    voice_call_id: str,
    filename: str = "",
    size_bytes: int = 0,
    source: str = "voice",
) -> None:
    entry = {
        "url": url,
        "data": None,
        "at": _now(),
        "voice_call_id": voice_call_id or "",
        "filename": filename,
        "size_bytes": size_bytes,
        "source": (source or "voice").strip() or "voice",
    }
    images: list[dict[str, Any]] = list(session.get("publishable_images") or [])
    images.append(entry)
    session["publishable_images"] = images[-8:]
    session["last_publishable_image"] = entry


def list_recent_publishable_images(
    user_id: str,
    *,
    max_age_sec: float = 300.0,
    ignore_call_binding: bool = True,
) -> list[dict[str, Any]]:
    """Imágenes recientes del HUD de voz; opcionalmente ignora voice_call_id."""
    session = _get(user_id)
    active_call = ensure_active_voice_call(user_id) if not ignore_call_binding else None
    with _lock:
        rows: list[dict[str, Any]] = list(session.get("publishable_images") or [])
        if not rows and session.get("last_publishable_image"):
            rows = [session["last_publishable_image"]]
        out: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            vid = str(row.get("voice_call_id") or "").strip()
            if not ignore_call_binding and active_call and vid and vid != active_call:
                continue
            age = _now() - float(row.get("at") or 0)
            if age > max_age_sec:
                continue
            url = str(row.get("url") or "").strip()
            data = str(row.get("data") or "").strip()
            if url or data:
                out.append(row)
        return out


def list_publishable_images(user_id: str, *, max_age_sec: float = 900.0) -> list[dict[str, Any]]:
    active_call = ensure_active_voice_call(user_id)
    session = _get(user_id)
    with _lock:
        rows: list[dict[str, Any]] = list(session.get("publishable_images") or [])
        if not rows and session.get("last_publishable_image"):
            rows = [session["last_publishable_image"]]
        out: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            vid = str(row.get("voice_call_id") or "").strip()
            if active_call and vid and vid != active_call:
                continue
            age = _now() - float(row.get("at") or 0)
            if age > max_age_sec:
                continue
            url = str(row.get("url") or "").strip()
            if url:
                out.append(row)
        return out


def set_last_publishable_image(
    user_id: str,
    *,
    image_url: str | None = None,
    image_data: str | None = None,
    awaiting_caption: bool = False,
    filename: str = "",
    size_bytes: int = 0,
    source: str = "voice",
) -> str | None:
    """Imagen del chat — disponible para publicar/analizar en voz Retell."""
    url = (image_url or "").strip()
    data = (image_data or "").strip()
    if not url and not data:
        return None
    call_id = ensure_active_voice_call(user_id) or ""
    session = _get(user_id)
    with _lock:
        img_source = (source or "voice").strip() or "voice"
        if url:
            _append_publishable_image(
                session,
                url=url,
                voice_call_id=call_id,
                filename=filename,
                size_bytes=size_bytes,
                source=img_source,
            )
        else:
            session["last_publishable_image"] = {
                "url": None,
                "data": data,
                "at": _now(),
                "voice_call_id": call_id,
                "filename": filename,
                "size_bytes": size_bytes,
                "source": img_source,
            }
        if awaiting_caption:
            session["awaiting_instagram_caption"] = True
        session["updated_at"] = _now()
        return url or None


def set_last_publishable_image_from_bytes(
    user_id: str,
    image_bytes: bytes,
    mime: str,
    *,
    awaiting_caption: bool = False,
    filename: str = "",
) -> str:
    """Guarda imagen del chat en disco + sesión voz (URL HTTPS para Meta)."""
    from app.services.publish_media import store_publish_image

    public_url = store_publish_image(user_id, image_bytes, mime)
    set_last_publishable_image(
        user_id,
        image_url=public_url,
        awaiting_caption=awaiting_caption,
        filename=filename,
        size_bytes=len(image_bytes),
    )
    try:
        from app.services.publish_image_context import register_voice_session_image

        register_voice_session_image(
            user_id,
            public_url,
            filename=filename,
            size_bytes=len(image_bytes),
        )
    except Exception:  # noqa: BLE001
        pass
    return public_url


def is_awaiting_instagram_caption(user_id: str) -> bool:
    session = _get(user_id)
    with _lock:
        if not str(session.get("active_voice_call_id") or "").strip():
            return False
        return bool(session.get("awaiting_instagram_caption"))


def clear_awaiting_instagram_caption(user_id: str) -> None:
    session = _get(user_id)
    with _lock:
        session["awaiting_instagram_caption"] = False
        session["updated_at"] = _now()


def get_last_publishable_image(
    user_id: str,
    *,
    max_age_sec: float = 900.0,
    ignore_call_binding: bool = False,
) -> dict[str, str] | None:
    active_call = ensure_active_voice_call(user_id) or ""
    session = _get(user_id)
    with _lock:
        row = session.get("last_publishable_image")
        if not row:
            return None
        source = str(row.get("source") or "").strip()
        bound_call = str(row.get("voice_call_id") or "").strip()
        if not ignore_call_binding and source != "chat":
            if bound_call and active_call and bound_call != active_call:
                return None
            if bound_call and not active_call:
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


def set_gmail_inbox_cache(user_id: str, messages: list[dict[str, Any]]) -> None:
    session = _get(user_id)
    with _lock:
        session["gmail_inbox_cache"] = deepcopy(messages or [])
        session["updated_at"] = _now()


def get_gmail_inbox_cache(user_id: str) -> list[dict[str, Any]]:
    rows = _get(user_id).get("gmail_inbox_cache")
    return deepcopy(rows) if isinstance(rows, list) else []


def set_gmail_awaiting_pick(user_id: str, awaiting: bool) -> None:
    session = _get(user_id)
    with _lock:
        session["gmail_awaiting_pick"] = bool(awaiting)
        if not awaiting:
            session["gmail_inbox_cache"] = []
        session["updated_at"] = _now()


def is_gmail_awaiting_pick(user_id: str) -> bool:
    return bool(_get(user_id).get("gmail_awaiting_pick"))


GMAIL_PENDING_TTL_SEC = 600


def set_gmail_pending_send(user_id: str, draft: dict[str, Any]) -> None:
    session = _get(user_id)
    now = _now()
    row = deepcopy(draft)
    row["prepared_at"] = now
    row["expires_at"] = now + GMAIL_PENDING_TTL_SEC
    with _lock:
        session["gmail_pending_send"] = row
        session["updated_at"] = now


def get_gmail_pending_send(user_id: str) -> dict[str, Any] | None:
    row = _get(user_id).get("gmail_pending_send")
    if not isinstance(row, dict):
        return None
    return deepcopy(row)


def is_gmail_pending_send_expired(user_id: str) -> bool:
    row = _get(user_id).get("gmail_pending_send")
    if not isinstance(row, dict):
        return False
    expires = float(row.get("expires_at") or 0)
    return expires > 0 and _now() > expires


def clear_gmail_pending_send(user_id: str, *, reason: str = "") -> None:
    session = _get(user_id)
    with _lock:
        session["gmail_pending_send"] = None
        session["updated_at"] = _now()


def try_mark_gmail_pending_sending(user_id: str, draft_id: str) -> bool:
    session = _get(user_id)
    with _lock:
        row = session.get("gmail_pending_send")
        if not isinstance(row, dict):
            return False
        if str(row.get("draft_id") or "") != draft_id:
            return False
        if str(row.get("status") or "") != "pending":
            return False
        row["status"] = "sending"
        session["gmail_pending_send"] = row
        session["updated_at"] = _now()
        return True


def mark_gmail_pending_sent(user_id: str, *, message_id: str = "") -> None:
    session = _get(user_id)
    with _lock:
        row = session.get("gmail_pending_send")
        if not isinstance(row, dict):
            return
        row["status"] = "sent"
        row["sent_message_id"] = message_id or None
        session["gmail_pending_send"] = row
        session["updated_at"] = _now()


def revert_gmail_pending_to_pending(user_id: str) -> None:
    session = _get(user_id)
    with _lock:
        row = session.get("gmail_pending_send")
        if not isinstance(row, dict):
            return
        if row.get("status") == "sending":
            row["status"] = "pending"
            session["gmail_pending_send"] = row
            session["updated_at"] = _now()


FINANCE_PENDING_TTL_SEC = 600


def set_finance_pending_write(user_id: str, draft: dict[str, Any]) -> None:
    session = _get(user_id)
    now = _now()
    row = deepcopy(draft)
    row["prepared_at"] = now
    row["expires_at"] = now + FINANCE_PENDING_TTL_SEC
    with _lock:
        session["finance_pending_write"] = row
        session["updated_at"] = now


def get_finance_pending_write(user_id: str) -> dict[str, Any] | None:
    row = _get(user_id).get("finance_pending_write")
    if not isinstance(row, dict):
        return None
    return deepcopy(row)


def is_finance_pending_write_expired(user_id: str) -> bool:
    row = _get(user_id).get("finance_pending_write")
    if not isinstance(row, dict):
        return False
    expires = float(row.get("expires_at") or 0)
    return expires > 0 and _now() > expires


def clear_finance_pending_write(user_id: str, *, reason: str = "") -> None:
    session = _get(user_id)
    with _lock:
        session["finance_pending_write"] = None
        session["updated_at"] = _now()


def try_mark_finance_pending_writing(user_id: str, draft_id: str) -> bool:
    session = _get(user_id)
    with _lock:
        row = session.get("finance_pending_write")
        if not isinstance(row, dict):
            return False
        if str(row.get("draft_id") or "") != draft_id:
            return False
        if str(row.get("status") or "") != "pending":
            return False
        row["status"] = "writing"
        session["finance_pending_write"] = row
        session["updated_at"] = _now()
        return True


def mark_finance_pending_written(user_id: str, *, saved_ids: list[str] | None = None) -> None:
    session = _get(user_id)
    with _lock:
        row = session.get("finance_pending_write")
        if not isinstance(row, dict):
            return
        row["status"] = "written"
        row["saved_ids"] = saved_ids or []
        session["finance_pending_write"] = row
        session["updated_at"] = _now()


def revert_finance_pending_to_pending(user_id: str) -> None:
    session = _get(user_id)
    with _lock:
        row = session.get("finance_pending_write")
        if not isinstance(row, dict):
            return
        if row.get("status") == "writing":
            row["status"] = "pending"
            session["finance_pending_write"] = row
            session["updated_at"] = _now()

