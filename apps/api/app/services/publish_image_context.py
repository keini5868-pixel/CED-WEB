"""Imágenes subidas en chat de texto — resolución para publicación Meta."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_by_conversation: dict[str, dict[str, Any]] = {}
_by_user: dict[str, dict[str, Any]] = {}
_vision_by_conversation: dict[str, dict[str, Any]] = {}

MAX_AGE_SEC = 3600.0
RECENT_UPLOAD_HOURS = 24.0
VOICE_RECENT_SEC = 300.0


def register_voice_session_image(
    user_id: str,
    public_url: str,
    *,
    filename: str = "",
    size_bytes: int = 0,
    session_id: str | None = None,
) -> None:
    """Registra imagen subida por HUD de voz para resolución cross-replica."""
    url = (public_url or "").strip()
    if not url:
        return
    uid = user_id.strip()
    entry = {
        "url": url,
        "data": None,
        "at": _now(),
        "filename": filename,
        "size_bytes": size_bytes,
        "source": "voice",
        "session_id": (session_id or "").strip() or None,
    }
    with _lock:
        _by_user[uid] = entry
    logger.info(
        "[PUBLISH] [IMAGE] voice upload registrada user=%s url=%s",
        uid[:8],
        url[:80],
    )


def get_last_voice_session_image(
    user_id: str,
    session_id: str | None = None,
    *,
    max_age_sec: float = MAX_AGE_SEC,
) -> dict[str, Any] | None:
    from app.services import voice_client_session as vcs

    uid = user_id.strip()
    recent_window = min(max_age_sec, VOICE_RECENT_SEC)

    stored = vcs.get_last_publishable_image(
        uid,
        max_age_sec=recent_window,
        ignore_call_binding=True,
    )
    if stored and (stored.get("url") or stored.get("data")):
        logger.info("[PUBLISH] [IMAGE] voice_session last_publishable user=%s", uid[:8])
        return {"url": stored.get("url"), "data": stored.get("data"), "source": "voice_session"}

    listed = vcs.list_recent_publishable_images(uid, max_age_sec=recent_window)
    if listed:
        row = listed[-1]
        logger.info("[PUBLISH] [IMAGE] voice_session list_recent user=%s", uid[:8])
        return {
            "url": row.get("url"),
            "data": row.get("data"),
            "source": "voice_session_list",
        }

    with _lock:
        row = _by_user.get(uid)
        if row and _now() - float(row.get("at") or 0) <= max_age_sec:
            logger.info("[PUBLISH] [IMAGE] publish_context user=%s", uid[:8])
            return dict(row)
    return None


def get_last_chat_conversation_image(
    user_id: str,
    conversation_id: str | None,
    *,
    max_age_sec: float = MAX_AGE_SEC,
) -> dict[str, Any] | None:
    if not conversation_id:
        return None
    uid = user_id.strip()
    now = _now()
    with _lock:
        row = _by_conversation.get(_conv_key(uid, conversation_id.strip()))
        if row and now - float(row.get("at") or 0) <= max_age_sec:
            return dict(row)
    return None


def get_last_user_upload(
    user_id: str,
    *,
    hours: float = RECENT_UPLOAD_HOURS,
) -> dict[str, Any] | None:
    return get_last_uploaded_image_for_session(user_id, None, max_age_sec=hours * 3600.0)


def _now() -> float:
    return time.time()


def _conv_key(user_id: str, conversation_id: str) -> str:
    return f"{user_id.strip()}:{conversation_id.strip()}"


def _store_entry(user_id: str, conversation_id: str, entry: dict[str, Any]) -> None:
    with _lock:
        _by_user[user_id.strip()] = entry
        cid = (conversation_id or "").strip()
        if cid:
            _by_conversation[_conv_key(user_id, cid)] = entry


def register_text_chat_image(
    user_id: str,
    conversation_id: str,
    image_bytes: bytes,
    mime: str,
    *,
    filename: str = "",
) -> str:
    """Persiste imagen del chat y devuelve URL pública para Meta."""
    from app.services.publish_media import store_publish_image

    public_url = store_publish_image(user_id, image_bytes, mime)
    entry = {
        "url": public_url,
        "data": bytes(image_bytes),
        "mime": (mime or "image/jpeg").split(";")[0].strip().lower() or "image/jpeg",
        "at": _now(),
        "conversation_id": conversation_id,
        "filename": filename,
        "size_bytes": len(image_bytes),
    }
    _store_entry(user_id, conversation_id, entry)
    _mirror_to_voice_session(user_id, public_url=public_url, filename=filename, size_bytes=len(image_bytes))
    return public_url


def register_text_chat_image_url(
    user_id: str,
    conversation_id: str,
    image_url: str,
    *,
    filename: str = "",
    preserve_reference_bytes: bool = True,
) -> str:
    url = (image_url or "").strip()
    if not url:
        return ""
    entry: dict[str, Any] = {
        "url": url,
        "data": None,
        "at": _now(),
        "conversation_id": conversation_id,
        "filename": filename,
        "size_bytes": 0,
    }
    if preserve_reference_bytes:
        existing = get_last_uploaded_image_for_session(user_id, conversation_id)
        if existing:
            data = existing.get("data")
            if isinstance(data, (bytes, bytearray)) and len(data) > 0:
                entry["data"] = bytes(data)
                entry["mime"] = existing.get("mime") or "image/jpeg"
                entry["size_bytes"] = len(entry["data"])
    _store_entry(user_id, conversation_id, entry)
    _mirror_to_voice_session(user_id, public_url=url, filename=filename)
    return url


def _mirror_to_voice_session(
    user_id: str,
    *,
    public_url: str,
    filename: str = "",
    size_bytes: int = 0,
) -> None:
    try:
        from app.services import voice_client_session as vcs

        vcs.set_last_publishable_image(
            user_id,
            image_url=public_url,
            filename=filename,
            size_bytes=size_bytes,
            source="chat",
        )
    except Exception:  # noqa: BLE001
        pass


def get_last_uploaded_image_for_session(
    user_id: str,
    conversation_id: str | None = None,
    *,
    max_age_sec: float = MAX_AGE_SEC,
) -> dict[str, Any] | None:
    uid = user_id.strip()
    now = _now()
    with _lock:
        if conversation_id:
            row = _by_conversation.get(_conv_key(uid, conversation_id))
            if row and now - float(row.get("at") or 0) <= max_age_sec:
                return dict(row)
        row = _by_user.get(uid)
        if row and now - float(row.get("at") or 0) <= max_age_sec:
            return dict(row)

    try:
        from app.services import voice_client_session as vcs

        stored = vcs.get_last_publishable_image(uid, max_age_sec=max_age_sec, ignore_call_binding=True)
        if stored:
            return {
                "url": stored.get("url"),
                "data": stored.get("data"),
                "at": now,
            }
    except Exception:  # noqa: BLE001
        pass
    return None


def has_publishable_image(user_id: str, conversation_id: str | None = None) -> bool:
    row = get_last_uploaded_image_for_session(user_id, conversation_id)
    if not row:
        return False
    return bool(str(row.get("url") or "").strip() or str(row.get("data") or "").strip())


def set_session_vision_analysis(
    user_id: str,
    conversation_id: str,
    analysis: str,
) -> None:
    """Cachea el último análisis visual de la conversación para generación con referencia."""
    text = (analysis or "").strip()
    if not text or not conversation_id:
        return
    key = _conv_key(user_id, conversation_id)
    with _lock:
        _vision_by_conversation[key] = {"analysis": text[:4000], "at": _now()}


def get_session_vision_analysis(
    user_id: str,
    conversation_id: str | None,
    *,
    max_age_sec: float = MAX_AGE_SEC,
) -> str:
    if not conversation_id:
        return ""
    key = _conv_key(user_id, conversation_id)
    now = _now()
    with _lock:
        row = _vision_by_conversation.get(key)
        if not row or now - float(row.get("at") or 0) > max_age_sec:
            return ""
        return str(row.get("analysis") or "").strip()


def resolve_reference_image_bytes(
    user_id: str,
    conversation_id: str | None,
    *,
    max_age_sec: float = MAX_AGE_SEC,
) -> tuple[bytes, str] | None:
    """Recupera bytes + MIME de la última imagen subida en la sesión de chat."""
    row = get_last_uploaded_image_for_session(user_id, conversation_id, max_age_sec=max_age_sec)
    if not row:
        return None

    data = row.get("data")
    mime = str(row.get("mime") or "image/jpeg").split(";")[0].strip().lower() or "image/jpeg"
    if isinstance(data, (bytes, bytearray)) and len(data) > 0:
        return bytes(data), mime

    url = str(row.get("url") or "").strip()
    if not url:
        return None
    try:
        from app.services.publish_media import decode_image_data

        fetched, fetched_mime = decode_image_data(url)
        if fetched:
            return fetched, fetched_mime or mime
    except Exception as exc:  # noqa: BLE001
        logger.warning("[PUBLISH] [IMAGE] fetch reference failed user=%s: %s", user_id[:8], exc)
    return None


def resolve_image_for_publishing(
    user_id: str,
    conversation_id: str | None = None,
    *,
    explicit_image_id: str | None = None,
    session_id: str | None = None,
    use_last_uploaded_image: bool = True,
    image_url: str | None = None,
    image_data: str | None = None,
) -> dict[str, Any]:
    url = (image_url or "").strip()
    if url:
        from app.services.publish_media import to_public_meta_image_url

        public = to_public_meta_image_url(url) or (
            url if url.startswith(("http://", "https://")) else ""
        )
        if public:
            return {"ok": True, "url": public, "data": None}

    data = str(image_data or "").strip()
    if data:
        return {"ok": True, "url": None, "data": data}

    eid = str(explicit_image_id or "").strip()
    if eid:
        from app.services.publish_media import to_public_meta_image_url

        public = to_public_meta_image_url(eid) or (
            eid if eid.startswith(("http://", "https://")) else ""
        )
        if public:
            return {"ok": True, "url": public, "data": None}

    if not use_last_uploaded_image:
        return _no_image_error()

    sid = str(session_id or "").strip() or None
    voice_img = get_last_voice_session_image(user_id, sid)
    if voice_img and (voice_img.get("url") or voice_img.get("data")):
        logger.info("[PUBLISH] imagen encontrada en voice session user=%s", user_id[:8])
        return _normalize_resolved_image(voice_img)

    chat_img = get_last_chat_conversation_image(user_id, conversation_id)
    if chat_img and (chat_img.get("url") or chat_img.get("data")):
        logger.info(
            "[PUBLISH] imagen encontrada en chat conv=%s user=%s",
            (conversation_id or "")[:8],
            user_id[:8],
        )
        return _normalize_resolved_image(chat_img)

    recent = get_last_user_upload(user_id, hours=RECENT_UPLOAD_HOURS)
    if recent and (recent.get("url") or recent.get("data")):
        logger.info("[PUBLISH] imagen encontrada en uploads recientes user=%s", user_id[:8])
        return _normalize_resolved_image(recent)

    try:
        from app.services.publish_media import find_latest_publish_media_url

        disk_url = find_latest_publish_media_url(user_id)
        if disk_url:
            logger.info("[PUBLISH] imagen encontrada en disco user=%s", user_id[:8])
            return {"ok": True, "url": disk_url, "data": None}
    except Exception:  # noqa: BLE001
        logger.warning("[PUBLISH] disk lookup failed user=%s", user_id[:8], exc_info=True)

    return _no_image_error()


def _normalize_resolved_image(row: dict[str, Any]) -> dict[str, Any]:
    from app.services.publish_media import to_public_meta_image_url

    raw_url = str(row.get("url") or "").strip()
    public = to_public_meta_image_url(raw_url) or (
        raw_url if raw_url.startswith(("http://", "https://")) else ""
    )
    return {
        "ok": True,
        "url": public or None,
        "data": row.get("data"),
    }


def _no_image_error() -> dict[str, Any]:
    return {
        "ok": False,
        "error": "no_image_available",
        "message": (
            "No hay imagen disponible para publicar. "
            "Pídale al usuario que suba una imagen al chat primero."
        ),
    }


def clear_session_image(user_id: str, conversation_id: str | None = None) -> None:
    uid = user_id.strip()
    with _lock:
        if conversation_id:
            _by_conversation.pop(_conv_key(uid, conversation_id), None)
        _by_user.pop(uid, None)


_publish_flows: dict[str, dict[str, Any]] = {}


def begin_publish_flow(
    user_id: str,
    conversation_id: str,
    *,
    platform: str,
    caption_draft: str = "",
    stage: str = "awaiting_caption_choice",
) -> None:
    key = _conv_key(user_id, conversation_id)
    with _lock:
        _publish_flows[key] = {
            "platform": platform,
            "caption_draft": caption_draft.strip(),
            "stage": stage,
            "at": _now(),
        }


def get_publish_flow(user_id: str, conversation_id: str) -> dict[str, Any] | None:
    key = _conv_key(user_id, conversation_id)
    with _lock:
        row = _publish_flows.get(key)
        if not row:
            return None
        if _now() - float(row.get("at") or 0) > MAX_AGE_SEC:
            _publish_flows.pop(key, None)
            return None
        return dict(row)


def update_publish_flow(
    user_id: str,
    conversation_id: str,
    *,
    caption_draft: str | None = None,
    stage: str | None = None,
    platform: str | None = None,
) -> None:
    key = _conv_key(user_id, conversation_id)
    with _lock:
        row = _publish_flows.get(key)
        if not row:
            return
        if caption_draft is not None:
            row["caption_draft"] = caption_draft.strip()
        if stage is not None:
            row["stage"] = stage
        if platform is not None:
            row["platform"] = platform.strip()
        row["at"] = _now()


def clear_publish_flow(user_id: str, conversation_id: str) -> None:
    with _lock:
        _publish_flows.pop(_conv_key(user_id, conversation_id), None)
