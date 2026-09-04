"""Respuesta WhatsApp con el mismo cerebro del chat de texto CED."""

from __future__ import annotations

import logging
import re

from app.services import supabase_db
from app.services.whatsapp_cognitive import analyze_turn

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
    mission: str = "",
) -> str:
    """Instrucciones + mensaje del contacto. No inventa datos de producto."""
    parts = [
        "Estás contestando por WhatsApp en nombre del dueño de ESTE número (esta cuenta CED).",
        "Usa el mismo criterio persuasivo y de conocimiento que en el chat de CED de esta cuenta.",
        "Combina el conocimiento interno de la cuenta (Castillo / producto) con búsqueda "
        "solo si la pregunta es técnica y no está en el manual. No inventes.",
        "No inventes precios, stock, políticas ni datos de producto que no estén en el conocimiento de la cuenta.",
        "Responde en texto corrido, breve y claro, sin tablas Markdown ni bloques de código.",
        "Máximo 8 frases salvo que pidan detalle. Una pregunta o siguiente paso por mensaje.",
    ]
    m = (mission or "").strip()
    if m:
        parts.append(m)
    g = (goal or "").strip()
    if g:
        parts.append(
            "Directriz de misión (la definió el dueño; persíguela según el ADN del prospecto, "
            f"sin un flujo rígido de burbujas): {g}"
        )
    else:
        parts.append(
            "El dueño aún no fijó una directriz: ayuda con claridad y avanza "
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


def reply_as_ced_chat(
    *,
    owner_user_id: str,
    wa_from: str,
    text: str,
    image_bytes: bytes | None = None,
    image_media_type: str | None = None,
) -> str:
    """Una respuesta de chat CED, acotada a texto WhatsApp."""
    from app.services.text_chat import TextChatError, send_message

    acc = supabase_db.get_whatsapp_account(owner_user_id) or {}
    contact = supabase_db.get_whatsapp_contact(owner_user_id, wa_from) or {}
    analysis = analyze_turn(
        text,
        previous_dna=str(contact.get("prospect_dna") or ""),
        previous_close=int(contact.get("close_score") or 0),
        opted_out=bool(contact.get("opted_out")),
        has_image=bool(image_bytes),
    )
    try:
        supabase_db.upsert_whatsapp_contact(
            owner_user_id,
            wa_from,
            {
                "prospect_dna": analysis["prospect_dna"],
                "sentiment": analysis["sentiment"],
                "close_score": analysis["close_score"],
                "leak_risk": analysis["leak_risk"],
                "human_alert": analysis["human_alert"],
            },
        )
    except Exception:  # noqa: BLE001
        logger.warning("[WA] no pude guardar ADN del prospecto")

    prompt = build_whatsapp_user_content(
        inbound_text=text,
        goal=str(acc.get("automation_goal") or ""),
        cta_url=str(acc.get("automation_cta_url") or ""),
        cta_label=str(acc.get("automation_cta_label") or ""),
        mission=str(analysis.get("overlay") or ""),
    )
    conversation_id = None
    stored = str(contact.get("conversation_id") or "").strip()
    if stored:
        conversation_id = stored
    try:
        kwargs: dict = {
            "content": prompt,
            "conversation_id": conversation_id,
        }
        if image_bytes:
            kwargs["image_bytes"] = image_bytes
            kwargs["image_media_type"] = (image_media_type or "image/jpeg").split(";")[0]
            kwargs["image_mode"] = "analyze"
        result = send_message(owner_user_id, **kwargs)
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
