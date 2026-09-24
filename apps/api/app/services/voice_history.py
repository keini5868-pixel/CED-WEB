"""Historial de voz en servidor — mismo destino que el chat, independiente del navegador."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def set_active_conversation(user_id: str, conversation_id: str | None) -> None:
    uid = (user_id or "").strip()
    cid = (conversation_id or "").strip()
    if not uid or not cid:
        return
    from app.services import voice_client_session as vcs

    vcs.set_conversation_id(uid, cid)


def get_active_conversation(user_id: str) -> str | None:
    uid = (user_id or "").strip()
    if not uid:
        return None
    from app.services import voice_client_session as vcs

    cid = vcs.get_conversation_id(uid)
    return cid or None


def ensure_voice_conversation_id(user_id: str) -> str | None:
    """Reutiliza el hilo abierto en el panel; no crea uno paralelo vacío."""
    uid = (user_id or "").strip()
    if not uid:
        return None
    existing = get_active_conversation(uid)
    if existing:
        return existing
    try:
        from app.services import supabase_db

        recent = supabase_db.list_conversations(uid, limit=1)
        latest_id = str((recent[0] or {}).get("id") or "").strip() if recent else ""
        if latest_id:
            set_active_conversation(uid, latest_id)
            logger.info("[VOICE-HIST] reusando hilo reciente conv=%s user=%s", latest_id[:8], uid[:8])
            return latest_id
        conv: dict[str, Any] = supabase_db.create_conversation(uid)
        cid = str(conv.get("id") or "").strip()
        if not cid:
            logger.error("[VOICE-HIST] create_conversation sin id user=%s", uid[:8])
            return None
        set_active_conversation(uid, cid)
        return cid
    except Exception as exc:  # noqa: BLE001
        logger.warning("[VOICE-HIST] create_conversation falló user=%s: %s", uid[:8], exc)
        return None


def persist_voice_turn(
    user_id: str,
    role: str,
    content: str,
    conversation_id: str | None = None,
) -> None:
    """Best-effort: guarda el turno en voice_messages aunque el cliente cierre."""
    uid = (user_id or "").strip()
    text = (content or "").strip()
    if not uid or not text:
        return
    if role not in ("user", "model", "system"):
        role = "model"
    forced = (conversation_id or "").strip()
    if forced:
        set_active_conversation(uid, forced)
    cid = ensure_voice_conversation_id(uid)
    if not cid:
        logger.warning("[VOICE-HIST] sin conversation_id — no se guardó %s user=%s", role, uid[:8])
        return
    try:
        from app.services import supabase_db

        supabase_db.append_message(cid, uid, role, text, channel="voice")
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[VOICE-HIST] append falló conv=%s role=%s: %s",
            cid[:8],
            role,
            exc,
        )


def sync_voice_transcript(
    user_id: str,
    utterances: list[dict[str, Any]] | None,
    conversation_id: str | None = None,
) -> None:
    """Replica el transcript de Retell (user + agent) en el mismo hilo del chat."""
    uid = (user_id or "").strip()
    if not uid:
        return
    turns: list[tuple[str, str]] = []
    for item in utterances or []:
        if not isinstance(item, dict):
            role = str(getattr(item, "role", "") or "").lower()
            content = str(getattr(item, "content", "") or getattr(item, "text", "") or "").strip()
        else:
            role = str(item.get("role") or "").lower()
            content = str(item.get("content") or item.get("text") or "").strip()
        if not content:
            continue
        turns.append(("user" if role in {"user", "customer"} else "model", content))
    if not turns:
        return
    forced = (conversation_id or "").strip()
    if forced:
        set_active_conversation(uid, forced)
    cid = ensure_voice_conversation_id(uid)
    if not cid:
        return
    try:
        from app.services import supabase_db

        supabase_db.sync_conversation_utterances(cid, uid, turns)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[VOICE-HIST] sync transcript falló user=%s: %s", uid[:8], exc)
