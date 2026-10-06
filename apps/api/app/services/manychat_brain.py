"""Cerebro CED para DMs de Instagram vía ManyChat."""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor
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
_POISON = re.compile(
    r"imagen recibida|el texto es el que acordamos|t[ií]tulo y la descripci[oó]n|"
    r"publicar[eé]|hashtags",
    re.I,
)
_DM_SYSTEM = (
    "Eres CED contestando un mensaje directo de Instagram por el dueño de la cuenta. "
    "Tutea. Nunca digas señor ni señora. No eres el asistente de voz. "
    "Si hay nombre, úsalo. No inventes nombres. "
    "2 a 4 frases. Una pregunta. Sin markdown. "
    "No hables de publicar fotos, títulos, descripciones ni imágenes recibidas."
)


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
    "asistente",
    "virtual",
    "ced",
    "admin",
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


def _fallback_greeting(
    contact_name: str,
    *,
    inbound: str = "",
    account: dict[str, Any] | None = None,
    first_turn: bool = True,
) -> str:
    acc = account or {}
    cta = str(acc.get("cta_url") or "").strip()
    label = str(acc.get("cta_label") or "grupo").strip()
    hi = f"{contact_name}, " if contact_name else ""
    low = (inbound or "").lower()
    if any(w in low for w in ("evento", "interesado", "saber", "trata", "más", "mas")):
        if cta:
            return (
                f"{hi}es un espacio para vender más con marketing digital: embudo, "
                f"videos y campañas. Si te late, entra a {label}: {cta}"
            )
        return (
            f"{hi}es sobre cómo vender más con marketing digital: tu embudo, "
            "tus videos y tus campañas. ¿Qué parte te interesa primero?"
        )
    if first_turn or low in {"hola", "info", "buenas", "hey"}:
        if contact_name:
            return (
                f"Hola {contact_name}, qué gusto tenerte por aquí. "
                "¿A qué te dedicas o qué vendes hoy?"
            )
        return "Hola, qué gusto tenerte por aquí. ¿A qué te dedicas o qué vendes hoy?"
    return f"{hi}cuéntame un poco más qué quieres resolver y te oriento."


def _haiku_dm_reply(prompt: str) -> str:
    import httpx

    from app.config import get_settings

    settings = get_settings()
    api_key = settings.anthropic_api_key.strip()
    if not api_key:
        raise RuntimeError("missing anthropic key")
    with httpx.Client(timeout=6.0) as client:
        res = client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 180,
                "system": _DM_SYSTEM,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        res.raise_for_status()
        data = res.json()
    parts = [
        str(block.get("text") or "")
        for block in (data.get("content") or [])
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    text = " ".join(parts).strip()
    if not text:
        raise RuntimeError("empty haiku")
    return text


def _gemini_dm_reply(prompt: str) -> str:
    from google import genai
    from google.genai import types

    from app.config import get_settings

    settings = get_settings()
    api_key = settings.google_api_key.strip()
    if not api_key:
        raise RuntimeError("missing google key")
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=_DM_SYSTEM,
            temperature=0.6,
            max_output_tokens=180,
        ),
    )
    text = (response.text or "").strip()
    if not text:
        raise RuntimeError("empty gemini")
    return text


def generate_dm_reply(
    prompt: str,
    *,
    contact_name: str = "",
    inbound: str = "",
    account: dict[str, Any] | None = None,
    first_turn: bool = True,
) -> str:
    """Respuesta corta para ManyChat: ManyChat corta a los ~10s."""
    fallback = _fallback_greeting(
        contact_name, inbound=inbound, account=account, first_turn=first_turn
    )
    for worker in (_haiku_dm_reply, _gemini_dm_reply):
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(worker, prompt)
            try:
                text = future.result(timeout=7.0)
            except Exception as exc:
                logger.warning("[MANYCHAT] %s fail: %s", worker.__name__, exc)
                continue
        if text and not _POISON.search(text):
            return text
    return fallback


def reply_as_ced(
    *,
    owner_user_id: str,
    account: dict[str, Any],
    payload: dict[str, Any],
) -> str:
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
        body = str(row.get("body") or "")
        if _POISON.search(body):
            continue
        who = "Contacto" if str(row.get("direction") or "") == "in" else "CED"
        thread.append(f"{who}: {body[:220]}")
    if thread:
        prompt = prompt + "\n\nConversación reciente:\n" + "\n".join(thread)
    try:
        raw = generate_dm_reply(
            prompt,
            contact_name=name,
            inbound=inbound,
            account=account,
            first_turn=first_turn,
        )
    except Exception:
        logger.exception("[MANYCHAT] chat CED exception")
        raw = ""
    reply = _plain(raw)
    reply = re.sub(r"\bseñora?s?\b[:,]?\s*", "", reply, flags=re.I)
    reply = " ".join(reply.split())
    if not reply or _POISON.search(reply):
        reply = _fallback_greeting(name)
    store.log_message(owner_user_id, sid, "out", reply)
    return reply
