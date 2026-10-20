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


def utterances_from_retell_call(call: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Normaliza transcript_object / transcript de un webhook o retrieve de Retell."""
    payload = call if isinstance(call, dict) else {}
    obj = payload.get("transcript_object") or payload.get("transcriptObject") or []
    rows: list[dict[str, Any]] = []
    if isinstance(obj, list):
        for entry in obj:
            if not isinstance(entry, dict):
                role = str(getattr(entry, "role", "") or "").lower()
                content = str(
                    getattr(entry, "content", "") or getattr(entry, "text", "") or ""
                ).strip()
            else:
                role = str(entry.get("role") or "").lower()
                content = str(entry.get("content") or entry.get("text") or "").strip()
            if not content:
                continue
            rows.append(
                {
                    "role": "user" if role in {"user", "customer"} else "agent",
                    "content": content,
                }
            )
    if rows:
        return rows
    raw = str(payload.get("transcript") or "").strip()
    if not raw:
        return []
    for line in raw.splitlines():
        text = line.strip()
        if not text:
            continue
        lower = text.lower()
        if lower.startswith("user:"):
            body = text.split(":", 1)[-1].strip()
            if body:
                rows.append({"role": "user", "content": body})
        elif lower.startswith("agent:") or lower.startswith("assistant:"):
            body = text.split(":", 1)[-1].strip()
            if body:
                rows.append({"role": "agent", "content": body})
    return rows


def persist_retell_call_transcript(
    user_id: str,
    conversation_id: str | None,
    call: dict[str, Any] | None,
    *,
    call_id: str | None = None,
) -> None:
    """Cierra el hueco del piloto nativo: el Custom LLM no corre, el webhook sí."""
    uid = (user_id or "").strip()
    cid_hint = (conversation_id or "").strip()
    utterances = utterances_from_retell_call(call)
    if not uid or not utterances:
        logger.info(
            "[VOICE-HIST] webhook sin transcript call=%s user=%s turns=%s",
            (call_id or "")[:12],
            uid[:8] if uid else "-",
            len(utterances),
        )
        return
    if cid_hint:
        set_active_conversation(uid, cid_hint)
    cid = ensure_voice_conversation_id(uid)
    if not cid:
        logger.warning(
            "[VOICE-HIST] webhook sin conversation_id call=%s user=%s",
            (call_id or "")[:12],
            uid[:8],
        )
        return
    if call_id:
        try:
            from app.services import supabase_db as _sdb

            _sdb.bind_retell_call(uid, cid, str(call_id).strip())
        except Exception as exc:  # noqa: BLE001
            logger.warning("[VOICE-HIST] bind_retell_call webhook falló: %s", exc)
    try:
        from app.services import supabase_db

        existing = supabase_db.get_conversation_messages(cid, uid, limit=200)
        first_role = "user" if utterances[0].get("role") in {"user", "customer"} else "model"
        first_text = str(utterances[0].get("content") or "").strip()
        baseline = len(existing)
        for i, row in enumerate(existing):
            role = "user" if str((row or {}).get("role") or "") == "user" else "model"
            content = str((row or {}).get("content") or "").strip()
            if role == first_role and content == first_text:
                baseline = i
                break
        tail = existing[baseline:]
        if len(tail) >= len(utterances):
            matched = True
            for i, item in enumerate(utterances):
                want_role = "user" if item.get("role") in {"user", "customer"} else "model"
                want_text = str(item.get("content") or "").strip()
                got = tail[i] or {}
                got_role = "user" if str(got.get("role") or "") == "user" else "model"
                if got_role != want_role or str(got.get("content") or "").strip() != want_text:
                    matched = False
                    break
            if matched:
                return
        supabase_db.sync_conversation_utterances(cid, uid, _utterance_pairs(utterances), baseline)
        logger.info(
            "[VOICE-HIST] webhook sync call=%s conv=%s turns=%s baseline=%s",
            (call_id or "")[:12],
            cid[:8],
            len(utterances),
            baseline,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[VOICE-HIST] webhook sync falló user=%s: %s", uid[:8], exc)


def _utterance_pairs(utterances: list[dict[str, Any]]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for item in utterances:
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        role = "user" if str(item.get("role") or "").lower() in {"user", "customer"} else "model"
        out.append((role, content))
    return out


def sync_voice_transcript(
    user_id: str,
    utterances: list[dict[str, Any]] | None,
    conversation_id: str | None = None,
    baseline: int | None = None,
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

        supabase_db.sync_conversation_utterances(cid, uid, turns, baseline)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[VOICE-HIST] sync transcript falló user=%s: %s", uid[:8], exc)
