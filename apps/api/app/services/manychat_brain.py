"""Cerebro CED para DMs de Instagram vía ManyChat."""

from __future__ import annotations

import logging
import re
from typing import Any

from app.services import manychat_store as store

logger = logging.getLogger(__name__)

ROLE_PRESETS: dict[str, dict[str, str]] = {
    "closer": {
        "label": "Cierre",
        "mission": (
            "Conversa en el DM. Pregunta qué busca, responde objeciones con claridad "
            "y avanza a un siguiente paso. Cuando la persona esté lista, comparte el enlace."
        ),
        "ask_lines": "¿Qué te interesa de esto?\n¿De dónde nos escribes?",
        "objections": (
            "Responde la duda en una o dos frases y vuelve a una pregunta de cierre. "
            "No insistas si pide hablar con un humano."
        ),
    },
    "qualifier": {
        "label": "Calificar",
        "mission": (
            "Solo califica. Haz 2-3 preguntas cortas para entender si encaja. "
            "No cierres fuerte hasta tener contexto."
        ),
        "ask_lines": "¿Qué estás buscando ahora?\n¿Ya conoces el producto o empiezas de cero?",
        "objections": "Aclara sin presionar. Si no encaja, agradece y no empujes el enlace.",
    },
    "support": {
        "label": "Soporte",
        "mission": (
            "Ayuda con claridad. Resuelve la duda. Si no sabes algo, dilo y ofrece el enlace "
            "solo si el dueño lo configuró y aporta."
        ),
        "ask_lines": "¿En qué te puedo ayudar?",
        "objections": "No discutas. Ofrece un siguiente paso o un humano.",
    },
    "custom": {
        "label": "Personalizado",
        "mission": "",
        "ask_lines": "",
        "objections": "",
    },
}

_MD_JUNK = re.compile(r"[#*_`>]{1,}")


def _plain(text: str) -> str:
    t = (text or "").strip()
    t = t.replace("**", "").replace("__", "")
    t = re.sub(r"^#+\s*", "", t, flags=re.M)
    t = re.sub(r"```[\s\S]*?```", " ", t)
    t = " ".join(t.split())
    if len(t) > 900:
        t = t[:890].rsplit(" ", 1)[0] + "…"
    return t


def inbound_text(payload: dict[str, Any]) -> str:
    for key in ("last_input_text", "text", "message", "input"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    nested = payload.get("message")
    if isinstance(nested, dict):
        text = nested.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()
    return ""


def subscriber_id(payload: dict[str, Any]) -> str:
    for key in ("subscriber_id", "id", "user_id", "key"):
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()[:120]
    return "unknown"


def display_name(payload: dict[str, Any]) -> str:
    name = payload.get("name") or payload.get("first_name") or ""
    return str(name).strip()[:80]


def build_behavior_prompt(account: dict[str, Any], inbound: str) -> str:
    role = str(account.get("role") or "closer")
    preset = ROLE_PRESETS.get(role) or ROLE_PRESETS["closer"]
    mission = (account.get("mission") or "").strip() or preset["mission"]
    asks = (account.get("ask_lines") or "").strip() or preset["ask_lines"]
    objections = (account.get("objections") or "").strip() or preset["objections"]
    never = (account.get("never_say") or "").strip()
    tone = str(account.get("tone") or "cercano")
    cta_url = str(account.get("cta_url") or "").strip()
    cta_label = str(account.get("cta_label") or "").strip()
    cta_when = str(account.get("cta_when") or "ready")

    parts = [
        "Estás contestando un mensaje directo en nombre del dueño de ESTA cuenta CED.",
        "ManyChat solo entrega el mensaje; TÚ eres el cerebro. Responde como CED de esta cuenta.",
        "Esto NO es publicar en redes ni editar una foto. No digas que recibiste una imagen.",
        "No ofrezcas título, descripción ni hashtags para una publicación.",
        "Texto corrido, breve, sin Markdown ni tablas. Máximo 5 frases. Una pregunta por mensaje.",
        "PROHIBIDO inventar precios, stock, políticas o datos que no estén en el conocimiento de la cuenta.",
        f"Tono: {tone}.",
        f"Rol: {preset['label']}.",
        f"Plantilla de comportamiento: {mission}",
    ]
    if asks:
        parts.append("Preguntas que puedes usar (no las dispares todas a la vez):\n" + asks)
    if objections:
        parts.append("Objeciones: " + objections)
    if never:
        parts.append("NUNCA digas ni hagas: " + never)
    if cta_url:
        hint = f"Enlace de cierre ({cta_label or 'grupo'}): {cta_url}"
        if cta_when == "always":
            parts.append(hint + " Inclúyelo en esta respuesta.")
        elif cta_when == "never":
            parts.append("Hay un enlace configurado pero NO lo envíes salvo que el contacto lo pida.")
        else:
            parts.append(
                hint + " Compártelo SOLO cuando la persona esté lista o lo pida "
                "(interés claro, pregunta por el grupo o por el siguiente paso)."
            )
    else:
        parts.append("El dueño aún no puso enlace de cierre. No inventes un grupo ni un wa.me.")
    parts.append("Mensaje del contacto:")
    parts.append(inbound.strip() or "(vacío)")
    return "\n".join(parts)


def manychat_response(
    *,
    text: str,
    callback_url: str,
    secret: str,
) -> dict[str, Any]:
    body = _plain(text) or "Aquí estoy. ¿En qué te ayudo?"
    return {
        "version": "v2",
        "content": {
            "type": "instagram",
            "messages": [{"type": "text", "text": body}],
            "actions": [],
            "quick_replies": [],
            "external_message_callback": {
                "url": callback_url,
                "method": "post",
                "payload": {
                    "last_input_text": "{{last_input_text}}",
                    "id": "{{user_id}}",
                    "secret": secret,
                },
                "timeout": 86400,
            },
        },
    }


def reply_as_ced(
    *,
    owner_user_id: str,
    account: dict[str, Any],
    payload: dict[str, Any],
) -> str:
    from app.services.text_chat import TextChatError, send_message

    inbound = inbound_text(payload)
    sid = subscriber_id(payload)
    name = display_name(payload)
    contact = store.get_contact(owner_user_id, sid) or {}
    store.upsert_contact(
        owner_user_id,
        sid,
        {"display_name": name, "last_text": inbound},
    )
    store.log_message(owner_user_id, sid, "in", inbound)
    prompt = build_behavior_prompt(account, inbound)
    conversation_id = str(contact.get("conversation_id") or "").strip() or None
    recent = store.list_messages(owner_user_id, limit=8)
    if any(
        str(row.get("subscriber_id") or "") == sid
        and str(row.get("direction") or "") == "out"
        and "imagen recibida" in str(row.get("body") or "").lower()
        for row in recent
    ):
        conversation_id = None
    try:
        result = send_message(
            owner_user_id,
            content=prompt,
            conversation_id=conversation_id,
            channel="manychat",
        )
    except TextChatError as exc:
        logger.warning("[MANYCHAT] chat CED falló: %s", exc)
        return "Ahora mismo no pude completar la respuesta. Escríbeme de nuevo en un momento."
    except Exception:
        logger.exception("[MANYCHAT] chat CED exception")
        return "Tuve un problema al responder. Inténtalo otra vez."
    cid = str(result.get("conversation_id") or "").strip()
    if cid:
        store.upsert_contact(owner_user_id, sid, {"conversation_id": cid, "display_name": name})
    reply = _plain(str(result.get("reply") or ""))
    store.log_message(owner_user_id, sid, "out", reply)
    return reply
