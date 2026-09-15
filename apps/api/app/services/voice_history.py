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
    """Crea o reutiliza la conversación de esta sesión de voz."""
    uid = (user_id or "").strip()
    if not uid:
        return None
    existing = get_active_conversation(uid)
    if existing:
        return existing
    try:
        from app.services import supabase_db

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


def persist_voice_turn(user_id: str, role: str, content: str) -> None:
    """Best-effort: guarda el turno en voice_messages aunque el cliente cierre."""
    uid = (user_id or "").strip()
    text = (content or "").strip()
    if not uid or not text:
        return
    if role not in ("user", "model", "system"):
        role = "model"
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
