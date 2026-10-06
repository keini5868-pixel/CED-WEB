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


_BAD_NAMES = {
    "",
    "subscriber",
    "user",
    "usuario",
    "instagram",
    "unknown",
    "contacto",
    "{{first_name}}",
    "{{name}}",
}


def first_name(payload: dict[str, Any], stored: str = "") -> str:
    nested = payload.get("custom_fields") if isinstance(payload.get("custom_fields"), dict) else {}
    raw = (
        payload.get("first_name")
        or payload.get("name")
        or payload.get("full_name")
        or nested.get("first_name")
        or stored
        or ""
    )
    token = str(raw).strip().split()[0] if str(raw).strip() else ""
    token = re.sub(r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ'-]", "", token)
    if token.lower() in _BAD_NAMES or len(token) < 2:
        return ""
    return token[:24]


def display_name(payload: dict[str, Any]) -> str:
    return first_name(payload)


def build_behavior_prompt(
    account: dict[str, Any],
    inbound: str,
    *,
    contact_name: str = "",
    first_turn: bool = True,
) -> str:
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
        "PROHIBIDO tratar de «señor», «señora» o de usted. Eso es solo el asistente de voz con el dueño.",
        "Tutea. Habla como un humano cercano, no como Jarvis ni como un bot de soporte.",
        f"Tono: {tone}.",
        f"Rol: {preset['label']}.",
        f"Plantilla de comportamiento: {mission}",
    ]
    if asks:
        parts.append("Preguntas que puedes usar (no las dispares todas a la vez):\n" + asks)
    if objections:
        parts.append("Objeciones: " + objections)
    if contact_name:
        if first_turn:
            parts.append(
                f"El contacto se llama {contact_name}. En ESTE primer mensaje salúdalo por su "
                f"nombre (ej. «Hola {contact_name}, qué gusto tenerte por aquí»). "
                "Luego una pregunta corta. No inventes otro nombre."
            )
        else:
            parts.append(
                f"El contacto se llama {contact_name}. Puedes usar su nombre con naturalidad, "
                "sin repetir «hola» cada turno."
            )
    else:
        parts.append(
            "No tenemos el nombre. Saluda sin «señor». Nunca inventes un nombre."
        )
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
                    "first_name": "{{first_name}}",
                    "name": "{{name}}",
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
    contact = store.get_contact(owner_user_id, sid) or {}
    name = first_name(payload, str(contact.get("display_name") or ""))
    prior = store.list_messages(owner_user_id, limit=16)
    first_turn = not any(
        str(row.get("subscriber_id") or "") == sid and str(row.get("direction") or "") == "in"
        for row in prior
    )
    store.upsert_contact(
        owner_user_id,
        sid,
        {"display_name": name, "last_text": inbound},
    )
    store.log_message(owner_user_id, sid, "in", inbound)
    prompt = build_behavior_prompt(
        account,
        inbound,
        contact_name=name,
        first_turn=first_turn,
    )
    thread = []
    for row in reversed(prior[:6]):
        if str(row.get("subscriber_id") or "") != sid:
            continue
        who = "Contacto" if str(row.get("direction") or "") == "in" else "CED"
        thread.append(f"{who}: {str(row.get('body') or '')[:220]}")
    if thread:
        prompt = prompt + "\n\nConversación reciente:\n" + "\n".join(thread)
    try:
        result = send_message(
            owner_user_id,
            content=prompt,
            conversation_id=None,
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
    reply = re.sub(r"\bseñora?s?\b[:,]?\s*", "", reply, flags=re.I)
    reply = " ".join(reply.split())
    store.log_message(owner_user_id, sid, "out", reply)
    return reply
