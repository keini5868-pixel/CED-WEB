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


def build_whatsapp_user_content(
    *,
    inbound_text: str,
    goal: str = "",
    cta_url: str = "",
    cta_label: str = "",
) -> str:
    """Instrucciones + mensaje del contacto. No inventa datos de producto."""
    parts = [
        "Estás contestando por WhatsApp en nombre del dueño de ESTE número (esta cuenta CED).",
        "Usa el mismo criterio persuasivo y de conocimiento que en el chat de CED de esta cuenta.",
        "No inventes precios, stock, políticas ni datos de producto que no estén en el conocimiento de la cuenta.",
        "Responde en texto corrido, breve y claro, sin tablas Markdown ni bloques de código.",
        "Máximo 8 frases salvo que pidan detalle. Una pregunta o siguiente paso por mensaje.",
    ]
    g = (goal or "").strip()
    if g:
        parts.append(
            "Objetivo de esta conversación (lo definió el dueño del número; "
            f"guía con naturalidad hacia esto, sin presionar en el primer mensaje si aún no hay interés): {g}"
        )
    else:
        parts.append(
            "El dueño aún no fijó un objetivo concreto: ayuda con claridad y avanza "
            "hacia una siguiente acción útil (agendar, pedir más info o dejar un enlace si ya lo conoces)."
        )
    url = (cta_url or "").strip()
    label = (cta_label or "").strip()
    if url:
        hint = f"Cuando la persona esté lista, comparte este enlace"
        if label:
            hint += f" ({label})"
        parts.append(f"{hint}: {url}")
    parts.append("Mensaje del contacto:")
    parts.append((inbound_text or "").strip() or "(vacío)")
    return "\n".join(parts)


def reply_as_ced_chat(*, owner_user_id: str, wa_from: str, text: str) -> str:
    """Una respuesta de chat CED, acotada a texto WhatsApp."""
    from app.services.text_chat import TextChatError, send_message

    acc = supabase_db.get_whatsapp_account(owner_user_id) or {}
    prompt = build_whatsapp_user_content(
        inbound_text=text,
        goal=str(acc.get("automation_goal") or ""),
        cta_url=str(acc.get("automation_cta_url") or ""),
        cta_label=str(acc.get("automation_cta_label") or ""),
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
