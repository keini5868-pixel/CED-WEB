"""Chat de texto con Claude — límites por plan."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any

import httpx

from app.config import get_settings
from app.domain.plans import get_plan_limits, normalize_plan_id
from app.services import supabase_db

logger = logging.getLogger(__name__)

CHAT_MODEL = "claude-sonnet-4-6"
CHAT_SYSTEM = """Eres CED (Castillo de la Evolución Digital), asistente inteligente en chat de texto.
Español latinoamericano natural, cálido y directo. NO uses "señor/señora" ni tono de mayordomo.
Responde con markdown cuando ayude (listas, negritas). Sé útil y conciso.
Nunca menciones Claude, Gemini ni APIs internas."""


class TextChatError(ValueError):
    pass


def _message_limit_for_user(user_id: str) -> int:
    from app.deps.auth import is_super_admin

    profile = supabase_db.get_profile(user_id) or {}
    if is_super_admin(profile.get("email"), profile.get("role")):
        return -1

    sub = supabase_db.get_subscription(user_id) or {}
    st = str(sub.get("status") or "")
    if st == "trialing":
        trial_end = sub.get("trial_ends_at")
        if trial_end:
            try:
                end = datetime.fromisoformat(str(trial_end).replace("Z", "+00:00"))
                if end > datetime.now(timezone.utc):
                    return -1
            except ValueError:
                pass

    plan_id = normalize_plan_id(sub.get("plan_id"))
    return get_plan_limits(plan_id).claude_messages_per_day


def count_user_messages_today(user_id: str, *, channel: str = "text") -> int:
    try:
        client = supabase_db._client()
        today = date.today().isoformat()
        convs = (
            client.table("voice_conversations")
            .select("id")
            .eq("user_id", user_id)
            .eq("channel", channel)
            .execute()
        )
        conv_ids = [c["id"] for c in (convs.data or [])]
        if not conv_ids:
            return 0
        msgs = (
            client.table("voice_messages")
            .select("id, created_at")
            .in_("conversation_id", conv_ids)
            .eq("role", "user")
            .gte("created_at", f"{today}T00:00:00")
            .execute()
        )
        return len(msgs.data or [])
    except Exception:  # noqa: BLE001
        return 0


def chat_status(user_id: str) -> dict[str, Any]:
    limit = _message_limit_for_user(user_id)
    used = count_user_messages_today(user_id)
    unlimited = limit < 0
    remaining = -1 if unlimited else max(0, limit - used)
    blocked = not unlimited and used >= limit
    return {
        "messages_used_today": used,
        "messages_limit_daily": limit if limit >= 0 else None,
        "unlimited": unlimited,
        "remaining_today": remaining if remaining >= 0 else None,
        "blocked": blocked,
    }


def _anthropic_messages(history: list[dict[str, str]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for row in history:
        role = row.get("role")
        content = (row.get("content") or "").strip()
        if not content:
            continue
        if role == "model":
            out.append({"role": "assistant", "content": content})
        elif role == "user":
            out.append({"role": "user", "content": content})
    return out[-20:]


def send_message(
    user_id: str,
    *,
    content: str,
    conversation_id: str | None = None,
) -> dict[str, Any]:
    text = content.strip()
    if not text:
        raise TextChatError("Mensaje vacío.")
    if len(text) > 8000:
        raise TextChatError("Mensaje demasiado largo.")

    status = chat_status(user_id)
    if status["blocked"]:
        raise TextChatError(
            "Alcanzaste el límite de mensajes de hoy. Mejora tu plan o vuelve mañana."
        )

    settings = get_settings()
    api_key = settings.anthropic_api_key.strip()
    if not api_key:
        raise TextChatError("Chat no configurado (ANTHROPIC_API_KEY).")

    if conversation_id:
        conv = supabase_db.get_conversation(conversation_id, user_id)
        if not conv or conv.get("channel") != "text":
            raise TextChatError("Conversación no encontrada.")
    else:
        title = text[:48] + ("…" if len(text) > 48 else "")
        conv = supabase_db.create_conversation(user_id, title=title, channel="text")
        conversation_id = str(conv["id"])

    history = supabase_db.get_conversation_messages(conversation_id, user_id, limit=30)
    supabase_db.append_message(conversation_id, user_id, "user", text)

    messages = _anthropic_messages(history)
    messages.append({"role": "user", "content": text})

    try:
        with httpx.Client(timeout=90.0) as client:
            res = client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": CHAT_MODEL,
                    "max_tokens": 1200,
                    "system": CHAT_SYSTEM,
                    "messages": messages,
                },
            )
            res.raise_for_status()
            data = res.json()
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        body = exc.response.text[:300]
        logger.error("[CHAT] anthropic %s %s", status, body)
        if status in (401, 403):
            raise TextChatError(
                "Chat no configurado: revisa ANTHROPIC_API_KEY en Railway (servicio CED-WEB)."
            ) from exc
        if status == 404:
            raise TextChatError(
                f"Modelo de chat no disponible ({CHAT_MODEL}). Contacta soporte."
            ) from exc
        raise TextChatError(
            "No pude obtener respuesta del asistente. Intenta de nuevo en un momento."
        ) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("[CHAT] anthropic failed")
        raise TextChatError("Error de conexión con el asistente.") from exc

    blocks = data.get("content") or []
    reply = "".join(
        b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text"
    ).strip()
    if not reply:
        raise TextChatError("Respuesta vacía del asistente.")

    supabase_db.append_message(conversation_id, user_id, "model", reply)
    updated_status = chat_status(user_id)

    return {
        "conversation_id": conversation_id,
        "reply": reply,
        "usage": updated_status,
    }
