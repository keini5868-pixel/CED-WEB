"""Respuesta WhatsApp con el mismo cerebro del chat de texto CED."""

from __future__ import annotations

import logging
import re

from app.services import supabase_db

logger = logging.getLogger(__name__)

_MD_JUNK = re.compile(r"[#*_`>]{1,}")


def _wa_plain(text: str) -> str:
    t = (text or "").strip()
    t = t.replace("**", "").replace("__", "")
    t = re.sub(r"^#+\s*", "", t, flags=re.M)
    t = re.sub(r"```[\s\S]*?```", " ", t)
    t = " ".join(t.split())
    if len(t) > 3500:
        t = t[:3490].rsplit(" ", 1)[0] + "…"
    return t


def reply_as_ced_chat(*, owner_user_id: str, wa_from: str, text: str) -> str:
    """Una respuesta de chat CED, acotada a texto WhatsApp."""
    from app.services.text_chat import TextChatError, send_message

    prompt = (
        "Estás contestando por WhatsApp. Responde en texto corrido, breve y claro, "
        "sin tablas Markdown ni bloques de código. Máximo 8 frases salvo que pidan detalle.\n\n"
        f"{(text or '').strip()}"
    )
    conversation_id = None
    contact = supabase_db.get_whatsapp_contact(owner_user_id, wa_from) or {}
    stored = str(contact.get("conversation_id") or "").strip()
    if stored:
        conversation_id = stored
    try:
        result = send_message(
            owner_user_id,
            content=prompt,
            conversation_id=conversation_id,
        )
    except TextChatError as exc:
        logger.warning("[WA] chat CED falló: %s", exc)
        return (
            "Ahora mismo no pude completar la respuesta automática. "
            "Escribe de nuevo en un momento."
        )
    except Exception:  # noqa: BLE001
        logger.exception("[WA] chat CED exception")
        return "Tuve un problema al responder. Inténtalo otra vez."

    cid = str(result.get("conversation_id") or "").strip()
    if cid and cid != stored:
        try:
            supabase_db.upsert_whatsapp_contact(
                owner_user_id,
                wa_from,
                {"conversation_id": cid},
            )
        except Exception:  # noqa: BLE001
            logger.warning("[WA] no pude guardar conversation_id")
    return _wa_plain(str(result.get("reply") or ""))
