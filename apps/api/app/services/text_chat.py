"""Chat de texto con Claude — límites por plan + herramientas Meta."""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from datetime import date, datetime, timezone
from typing import Any

import httpx

from app.config import get_settings
from app.services import supabase_db
from app.services.cognitive_intents import has_advanced_confirmation
from app.services.cognitive_router import build_chat_system_extras, route_message
from app.services.chat_intents import (
    is_generate_image_intent,
    is_pdf_intent,
    parse_generate_image_prompt,
    parse_pdf_request,
)
from app.services.claude_deep_analysis import consultar_sistema_avanzado
from app.domain.ced_identity import (
    CED_CORE_IDENTITY,
    CED_CREATOR_IDENTITY,
    CED_HUMAN_VOICE_STYLE,
)
from app.domain.ced_memory_prompt import CED_MEMORY_USAGE_RULES
from app.domain.ced_sales_mentor import CED_SALES_MENTOR_CORE
from app.domain.ced_viral_knowledge import CED_VIRAL_KNOWLEDGE_2026
from app.services.meta_social import MetaSocialError, publish_facebook, publish_instagram
from app.services.pdf_report import store_pdf

logger = logging.getLogger(__name__)

CHAT_MODEL = "claude-sonnet-4-6"
CHAT_MODEL_FAST = "claude-3-5-haiku-20241022"
CHAT_HISTORY_LIMIT = 14
CHAT_SIMPLE_MAX_TOKENS = 700
CHAT_TOOLS_MAX_TOKENS = 1000

_VIRAL_KEYWORDS = re.compile(
    r"\b(instagram|tiktok|reels?|viral|horario|publicar|contenido|linkedin|facebook|"
    r"hooks?|stories|algoritmo|engagement|redes\s+sociales)\b",
    re.I,
)
_TOOLS_KEYWORDS = re.compile(
    r"\b(publica|publicar|instagram|facebook|meta|recuerdas|guarda|memoria|"
    r"lead|cliente|pdf|imagen|conectad)\b",
    re.I,
)

CHAT_TOOLS: list[dict[str, Any]] = [
    {
        "name": "consultar_redes_conectadas",
        "description": "Consulta si Facebook/Instagram están conectados a CED para este usuario.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "publicar_facebook",
        "description": "Publica un post en la página de Facebook conectada del usuario.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Texto del post"},
                "image_url": {
                    "type": "string",
                    "description": "URL HTTPS pública de imagen opcional",
                },
            },
            "required": ["message"],
        },
    },
    {
        "name": "publicar_instagram",
        "description": "Publica en Instagram Business conectado. Requiere imagen con URL HTTPS pública.",
        "input_schema": {
            "type": "object",
            "properties": {
                "caption": {"type": "string", "description": "Caption del post"},
                "image_url": {
                    "type": "string",
                    "description": "URL HTTPS pública de la imagen (obligatoria en IG)",
                },
            },
            "required": ["caption", "image_url"],
        },
    },
    {
        "name": "generar_pdf",
        "description": (
            "Genera un PDF descargable. OBLIGATORIO: el campo content debe contener "
            "TODO el texto del documento (resumen, lista, informe completo). "
            "Nunca dejes content vacío ni solo con el título."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Título del documento PDF"},
                "content": {
                    "type": "string",
                    "description": "Cuerpo COMPLETO del PDF — todo el texto que el usuario quiere guardar",
                },
            },
            "required": ["title", "content"],
        },
    },
    {
        "name": "generate_image",
        "description": (
            "Genera una imagen con IA. Usar cuando pidan crear, diseñar o generar una imagen. "
            "Tras generar, confirma brevemente; la app muestra la imagen automáticamente."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Descripción detallada de la imagen"},
                "quality": {
                    "type": "string",
                    "enum": ["auto", "standard", "hd"],
                    "description": "Calidad opcional",
                },
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "recall_previous_conversations",
        "description": (
            "Busca en conversaciones previas. Usar cuando referencien el pasado "
            "o pregunten '¿recuerdas cuando…?'"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "days_back": {"type": "integer"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "save_to_long_term_memory",
        "description": (
            "Guarda datos importantes para futuras sesiones (leads, metas, proyectos). "
            "Silencioso — no anunciar."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": [
                        "business",
                        "personal",
                        "goal",
                        "preference",
                        "fact",
                        "project",
                        "lead",
                    ],
                },
                "key": {"type": "string"},
                "value": {"type": "string"},
                "importance": {"type": "integer"},
            },
            "required": ["category", "key", "value"],
        },
    },
]

CHAT_SYSTEM_BASE = f"""Eres CED (Castillo de la Evolución Digital), asistente dentro de la plataforma CED Web.
Español latinoamericano natural, cálido y directo.
Responde con markdown cuando ayude. Sé útil y conciso. Nunca menciones Claude, Gemini ni APIs internas.

{CED_CORE_IDENTITY}

{CED_CREATOR_IDENTITY}

{CED_HUMAN_VOICE_STYLE}

{CED_SALES_MENTOR_CORE}

IMPORTANTE — tratamiento del usuario:
- Usa el nombre y título del bloque "USUARIO ACTUAL — TRATAMIENTO" inyectado abajo.
- Si piden "llámame señor/señora/jefe/etc.", confirma y recuerda con save_memory key "tratamiento".
- NO uses tono de mayordomo exagerado; Señor/Señora solo si el usuario lo prefiere.

IMPORTANTE — cerebro híbrido CED:
- Primero usa conocimiento interno estable (conceptos, negocio, ciencia, cultura) cuando viene en el contexto.
- Solo afirma datos de hoy (clima, precios, noticias) si hay contexto web inyectado abajo.
- Sistema avanzado: si el contexto indica confirmación pendiente, pregunta antes de profundizar.

IMPORTANTE — capacidades REALES de esta plataforma:
- CED puede publicar en Facebook e Instagram cuando el usuario conectó Meta (dashboard → Conectar Redes).
- Usa las herramientas publicar_facebook / publicar_instagram cuando el usuario pida publicar y tengas los datos.
- Si falta caption o image_url (Instagram), pídelos antes de invocar la herramienta.
- Si las redes NO están conectadas, indica conectar en el dashboard — NO digas que es imposible en absoluto.
- Puedes generar PDFs descargables con generar_pdf. El campo content debe incluir TODO el texto del documento, no solo el título.
- Puedes GENERAR IMÁGENES con generate_image cuando pidan crear/diseñar una imagen. Invoca la herramienta; la app muestra la imagen en el chat.
- NUNCA escribas URLs /v1/pdf/download en tu respuesta. Di que el PDF está listo; la app muestra el botón Descargar automáticamente.

PROHIBIDO (respuestas de chatbot genérico):
- "No tengo acceso a internet en tiempo real" — CED tiene búsqueda y herramientas en voz; en chat puedes preparar contenido y publicar vía Meta.
- "No me puedo conectar a tus cuentas" — sí puedes vía Meta OAuth cuando está conectado.
- Recomendar Buffer/Hootsuite como única opción si el usuario ya tiene CED con redes conectadas.

Cuando prepares contenido para redes, entrégalo listo y ofrece publicarlo con CED si aplica."""


def _wants_viral_knowledge(text: str) -> bool:
    return bool(_VIRAL_KEYWORDS.search(text or ""))


def _needs_chat_tools(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if is_pdf_intent(t) or is_generate_image_intent(t):
        return False
    return bool(_TOOLS_KEYWORDS.search(t))


def _build_chat_system(
    user_id: str,
    user_text: str,
    route: Any | None = None,
) -> str:
    parts = [_chat_system_for_user(user_id)]
    if _wants_viral_knowledge(user_text):
        parts.append(CED_VIRAL_KNOWLEDGE_2026)
        parts.append(CED_MEMORY_USAGE_RULES)
    extras = build_chat_system_extras(user_id, route)
    if extras:
        parts.append(extras)
    return "\n\n".join(parts)


def _chat_system_for_user(user_id: str) -> str:
    conn = supabase_db.get_meta_connection(user_id)
    if conn and conn.get("access_token"):
        username = conn.get("ig_username") or "Instagram"
        return (
            f"{CHAT_SYSTEM_BASE}\n\n"
            f"Estado Meta del usuario: CONECTADO (@{username}). "
            "Puedes publicar con las herramientas cuando confirme el texto."
        )
    return (
        f"{CHAT_SYSTEM_BASE}\n\n"
        "Estado Meta del usuario: NO conectado. "
        "Para publicar directo, debe usar Conectar Redes en el dashboard."
    )


class TextChatError(ValueError):
    """Error de chat con código HTTP sugerido para la API."""

    def __init__(self, message: str, *, http_status: int = 400) -> None:
        super().__init__(message)
        self.http_status = http_status
    pass


def _message_limit_for_user(user_id: str) -> int:
    from app.deps.plan_access import chat_message_limit

    return chat_message_limit(user_id)


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
    from app.services.admin_users import get_user_access

    allowed, reason, _ = get_user_access(user_id)
    if not allowed and reason == "trial_expired":
        used = count_user_messages_today(user_id)
        return {
            "messages_used_today": used,
            "messages_limit_daily": 0,
            "unlimited": False,
            "remaining_today": 0,
            "blocked": True,
            "trial_expired": True,
        }

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


def _run_chat_tool(user_id: str, name: str, tool_input: dict[str, Any]) -> str:
    try:
        if name == "consultar_redes_conectadas":
            conn = supabase_db.get_meta_connection(user_id)
            if not conn or not conn.get("access_token"):
                return json.dumps({"connected": False})
            return json.dumps(
                {
                    "connected": True,
                    "instagram_username": conn.get("ig_username"),
                    "page_id": conn.get("page_id"),
                }
            )
        if name == "publicar_facebook":
            result = publish_facebook(
                user_id,
                str(tool_input.get("message") or ""),
                image_url=tool_input.get("image_url"),
                image_data=tool_input.get("image_data"),
            )
            return json.dumps(result)
        if name == "publicar_instagram":
            result = publish_instagram(
                user_id,
                str(tool_input.get("caption") or ""),
                image_url=tool_input.get("image_url"),
                image_data=tool_input.get("image_data"),
            )
            return json.dumps(result)
        if name == "generar_pdf":
            from app.deps.plan_access import effective_plan_limits

            limits, reason, _ = effective_plan_limits(user_id)
            if reason == "trial_expired":
                return json.dumps(
                    {"ok": False, "error": "Tu prueba terminó. Elige un plan en Precios."},
                )
            if not limits.pdf_reports:
                return json.dumps(
                    {
                        "ok": False,
                        "error": "Los PDFs requieren plan Élite o Founding. Mejora en /pricing.",
                    },
                )
            title = str(tool_input.get("title") or "Documento CED").strip()
            content = str(tool_input.get("content") or "").strip()
            if not content or len(content) < 3:
                content = title
            artifact = store_pdf(user_id=user_id, title=title, content=content)
            return json.dumps(
                {
                    "ok": True,
                    "file_id": artifact.file_id,
                    "filename": artifact.filename,
                    "title": artifact.title,
                    "download_path": f"/v1/pdf/download/{artifact.file_id}",
                }
            )
        if name == "generate_image":
            from app.services.openai_images import generate_image

            plan_id = None
            try:
                sub = supabase_db.get_subscription(user_id)
                plan_id = sub.get("plan_id") if sub else None
            except Exception:  # noqa: BLE001
                pass
            prompt = str(tool_input.get("prompt") or "").strip()
            quality = str(tool_input.get("quality") or "auto")
            result = generate_image(
                user_id=user_id,
                plan_id=plan_id,
                prompt=prompt,
                quality=quality,
            )
            if result.get("ok") and result.get("url"):
                result["prompt"] = prompt
            return json.dumps(result)
        if name == "recall_previous_conversations":
            from app.services.conversation_memory import (
                format_recall_for_voice,
                recall_previous_conversations,
            )

            query = str(tool_input.get("query") or "").strip()
            days = int(tool_input.get("days_back") or 30)
            data = recall_previous_conversations(user_id, query, days_back=days)
            return json.dumps({**data, "spoken": format_recall_for_voice(data)})
        if name == "save_to_long_term_memory":
            from app.services.conversation_memory import save_long_term_memory

            return json.dumps(
                save_long_term_memory(
                    user_id,
                    category=str(tool_input.get("category") or "fact"),
                    key=str(tool_input.get("key") or ""),
                    value=str(tool_input.get("value") or ""),
                    importance=int(tool_input.get("importance") or 5),
                )
            )
        return json.dumps({"error": f"Herramienta desconocida: {name}"})
    except MetaSocialError as exc:
        return json.dumps({"ok": False, "error": str(exc)})
    except Exception as exc:  # noqa: BLE001
        logger.exception("[CHAT] tool %s failed", name)
        return json.dumps({"ok": False, "error": str(exc)[:200]})


def _anthropic_request(
    *,
    api_key: str,
    system: str,
    messages: list[dict[str, Any]],
    model: str = CHAT_MODEL,
    max_tokens: int = CHAT_TOOLS_MAX_TOKENS,
    with_tools: bool = True,
    timeout: float = 90.0,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": messages,
    }
    if with_tools:
        payload["tools"] = CHAT_TOOLS
    with httpx.Client(timeout=timeout) as client:
        res = client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=payload,
        )
        res.raise_for_status()
        return res.json()


def _anthropic_simple_reply(
    *,
    api_key: str,
    system: str,
    messages: list[dict[str, Any]],
) -> str:
    data = _anthropic_request(
        api_key=api_key,
        system=system,
        messages=messages,
        model=CHAT_MODEL_FAST,
        max_tokens=CHAT_SIMPLE_MAX_TOKENS,
        with_tools=False,
        timeout=45.0,
    )
    reply = _final_text_from_response(data)
    if not reply:
        raise TextChatError("Respuesta vacía del asistente.")
    return reply


def _openai_simple_reply(
    *,
    api_key: str,
    model: str,
    system: str,
    messages: list[dict[str, Any]],
) -> str:
    oai_messages = [{"role": "system", "content": system}]
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content")
        if role in ("user", "assistant") and isinstance(content, str):
            oai_messages.append({"role": role, "content": content})
    with httpx.Client(timeout=45.0) as client:
        res = client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": CHAT_SIMPLE_MAX_TOKENS,
                "messages": oai_messages,
            },
        )
        res.raise_for_status()
        data = res.json()
    choice = (data.get("choices") or [{}])[0]
    reply = str((choice.get("message") or {}).get("content") or "").strip()
    if not reply:
        raise TextChatError("Respuesta vacía del asistente.")
    return reply


def _final_text_from_response(data: dict[str, Any]) -> str:
    blocks = data.get("content") or []
    return "".join(
        b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text"
    ).strip()


def _pdf_attachment_from_artifact(artifact: Any) -> dict[str, Any]:
    return {
        "file_id": artifact.file_id,
        "filename": artifact.filename,
        "title": artifact.title,
        "download_path": f"/v1/pdf/download/{artifact.file_id}",
    }


def _strip_pdf_markdown_links(text: str) -> str:
    cleaned = re.sub(
        r"\[([^\]]*)\]\([^)]*\/pdf\/download\/[a-f0-9]+[^)]*\)",
        "",
        text,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"https?://[^\s)]+(?:/v1/pdf|/api/ced/pdf)/download/[a-f0-9]+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"/(?:v1/pdf|api/ced/pdf)/download/[a-f0-9]+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _extract_pdf_from_tool_result(result: str) -> dict[str, Any] | None:
    try:
        data = json.loads(result)
    except json.JSONDecodeError:
        return None
    if isinstance(data, dict) and data.get("ok") and data.get("file_id"):
        return {
            "file_id": data["file_id"],
            "filename": data.get("filename") or "documento.pdf",
            "title": data.get("title") or "Documento CED",
            "download_path": data.get("download_path"),
        }
    return None


def _extract_image_from_tool_result(result: str) -> dict[str, Any] | None:
    try:
        data = json.loads(result)
    except json.JSONDecodeError:
        return None
    if isinstance(data, dict) and data.get("ok") and data.get("url"):
        return {
            "url": str(data["url"]),
            "prompt": data.get("prompt"),
            "quality": data.get("quality"),
        }
    return None


def _advanced_confirm_followup(history: list[dict[str, str]], user_reply: str) -> str | None:
    """Si el usuario confirmó sistema avanzado, devuelve la pregunta original."""
    if not has_advanced_confirmation(user_reply):
        return None
    last_model: str | None = None
    for row in reversed(history):
        if row.get("role") == "model":
            last_model = (row.get("content") or "").strip()
            break
    if not last_model or not re.search(r"sistema avanzado|confirma", last_model, re.I):
        return None
    seen_model = False
    for row in reversed(history):
        role = row.get("role")
        content = (row.get("content") or "").strip()
        if not content:
            continue
        if role == "model" and content == last_model:
            seen_model = True
            continue
        if seen_model and role == "user":
            return content
    return None


def _openai_tools_format() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["input_schema"],
            },
        }
        for tool in CHAT_TOOLS
    ]


def _openai_request(
    *,
    api_key: str,
    model: str,
    system: str,
    messages: list[dict[str, Any]],
) -> dict[str, Any]:
    with httpx.Client(timeout=90.0) as client:
        res = client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": 1200,
                "messages": [{"role": "system", "content": system}, *messages],
                "tools": _openai_tools_format(),
            },
        )
        res.raise_for_status()
        return res.json()


def _complete_chat_with_tools_openai(
    user_id: str,
    *,
    api_key: str,
    model: str,
    system: str,
    messages: list[dict[str, Any]],
) -> tuple[str, dict[str, Any] | None, dict[str, Any] | None]:
    pdf_attachment: dict[str, Any] | None = None
    image_attachment: dict[str, Any] | None = None
    working = list(messages)
    for _ in range(4):
        data = _openai_request(
            api_key=api_key,
            model=model,
            system=system,
            messages=working,
        )
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            reply = str(message.get("content") or "").strip()
            if reply:
                if pdf_attachment:
                    reply = _strip_pdf_markdown_links(reply)
                return reply, pdf_attachment, image_attachment
            raise TextChatError("Respuesta vacía del asistente.")

        working.append(message)
        for tool in tool_calls:
            fn = tool.get("function") or {}
            name = str(fn.get("name") or "")
            raw_args = fn.get("arguments") or "{}"
            try:
                tool_input = json.loads(raw_args) if isinstance(raw_args, str) else {}
            except json.JSONDecodeError:
                tool_input = {}
            if not isinstance(tool_input, dict):
                tool_input = {}
            result = _run_chat_tool(user_id, name, tool_input)
            maybe_pdf = _extract_pdf_from_tool_result(result)
            if maybe_pdf:
                pdf_attachment = maybe_pdf
            maybe_img = _extract_image_from_tool_result(result)
            if maybe_img:
                image_attachment = maybe_img
            working.append(
                {
                    "role": "tool",
                    "tool_call_id": tool.get("id"),
                    "content": result,
                }
            )

    raise TextChatError("Demasiados pasos de herramientas. Intenta con un pedido más simple.")


def _complete_chat_with_tools(
    user_id: str,
    *,
    api_key: str,
    system: str,
    messages: list[dict[str, Any]],
) -> tuple[str, dict[str, Any] | None, dict[str, Any] | None]:
    pdf_attachment: dict[str, Any] | None = None
    image_attachment: dict[str, Any] | None = None
    for _ in range(4):
        data = _anthropic_request(api_key=api_key, system=system, messages=messages)
        blocks = data.get("content") or []
        tool_uses = [b for b in blocks if isinstance(b, dict) and b.get("type") == "tool_use"]
        if not tool_uses:
            reply = _final_text_from_response(data)
            if reply:
                if pdf_attachment:
                    reply = _strip_pdf_markdown_links(reply)
                return reply, pdf_attachment, image_attachment
            raise TextChatError("Respuesta vacía del asistente.")

        messages.append({"role": "assistant", "content": blocks})
        tool_results: list[dict[str, Any]] = []
        for tool in tool_uses:
            tool_input = tool.get("input") if isinstance(tool.get("input"), dict) else {}
            result = _run_chat_tool(user_id, str(tool.get("name") or ""), tool_input)
            maybe_pdf = _extract_pdf_from_tool_result(result)
            if maybe_pdf:
                pdf_attachment = maybe_pdf
            maybe_img = _extract_image_from_tool_result(result)
            if maybe_img:
                image_attachment = maybe_img
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tool.get("id"),
                    "content": result,
                }
            )
        messages.append({"role": "user", "content": tool_results})

    raise TextChatError("Demasiados pasos de herramientas. Intenta con un pedido más simple.")


def _complete_chat_resilient(
    user_id: str,
    *,
    user_text: str,
    anthropic_key: str,
    openai_key: str,
    openai_model: str,
    system: str,
    messages: list[dict[str, Any]],
) -> tuple[str, dict[str, Any] | None, dict[str, Any] | None]:
    """Ruta rápida sin tools para chat normal; tools solo cuando hace falta."""
    if not _needs_chat_tools(user_text):
        if anthropic_key:
            try:
                reply = _anthropic_simple_reply(
                    api_key=anthropic_key,
                    system=system,
                    messages=messages,
                )
                return reply, None, None
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code not in (401, 403) or not openai_key:
                    raise
                logger.warning("[CHAT] Haiku failed — fallback OpenAI mini")
        if openai_key:
            settings = get_settings()
            lite = settings.openai_model_chat_lite.strip() or "gpt-4o-mini"
            reply = _openai_simple_reply(
                api_key=openai_key,
                model=lite,
                system=system,
                messages=messages,
            )
            return reply, None, None

    if anthropic_key:
        try:
            return _complete_chat_with_tools(
                user_id,
                api_key=anthropic_key,
                system=system,
                messages=messages,
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (401, 403) and openai_key:
                logger.warning("[CHAT] Anthropic auth failed — fallback OpenAI")
            else:
                raise
    if openai_key:
        return _complete_chat_with_tools_openai(
            user_id,
            api_key=openai_key,
            model=openai_model,
            system=system,
            messages=messages,
        )
    raise TextChatError(
        "Servicio de chat temporalmente no disponible. Intenta de nuevo en unos minutos.",
        http_status=503,
    )


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
    if status.get("trial_expired"):
        raise TextChatError(
            "Tu prueba terminó. Elige un plan en Precios o continúa con el plan Básico gratis."
        )
    if status["blocked"]:
        raise TextChatError(
            "Alcanzaste el límite de mensajes de hoy. Mejora tu plan o vuelve mañana.",
            http_status=429,
        )

    settings = get_settings()
    anthropic_key = settings.anthropic_api_key.strip()
    openai_key = settings.openai_api_key.strip()
    if not anthropic_key and not openai_key:
        raise TextChatError(
            "Servicio de chat temporalmente no disponible. Intenta de nuevo en unos minutos.",
            http_status=503,
        )

    if conversation_id:
        conv = supabase_db.get_conversation(conversation_id, user_id)
        if not conv or conv.get("channel") != "text":
            raise TextChatError("Conversación no encontrada.")
    else:
        title = text[:48] + ("…" if len(text) > 48 else "")
        conv = supabase_db.create_conversation(user_id, title=title, channel="text")
        conversation_id = str(conv["id"])

    history = supabase_db.get_conversation_messages(
        conversation_id, user_id, limit=CHAT_HISTORY_LIMIT,
    )
    supabase_db.append_message(
        conversation_id,
        user_id,
        "user",
        text,
        session_id=conversation_id,
        channel="text",
    )

    def _finish(
        reply: str,
        *,
        route_meta: dict | None = None,
        pdf: dict[str, Any] | None = None,
        image: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        supabase_db.append_message(
            conversation_id,
            user_id,
            "model",
            reply,
            session_id=conversation_id,
            channel="text",
        )
        updated_status = chat_status(user_id)
        out: dict[str, Any] = {
            "conversation_id": conversation_id,
            "reply": reply,
            "usage": updated_status,
        }
        if route_meta:
            out["cognitive"] = route_meta
        if pdf:
            out["pdf"] = pdf
        if image:
            out["image"] = image
        return out

    img_prompt = parse_generate_image_prompt(text)
    if img_prompt and is_generate_image_intent(text) and openai_key:
        from app.services.openai_images import generate_image

        plan_id = None
        try:
            sub = supabase_db.get_subscription(user_id)
            plan_id = sub.get("plan_id") if sub else None
        except Exception:  # noqa: BLE001
            pass
        img_result = generate_image(
            user_id=user_id,
            plan_id=plan_id,
            prompt=img_prompt,
            quality="auto",
        )
        if img_result.get("ok") and img_result.get("url"):
            return _finish(
                "Listo. Aquí está tu imagen generada.",
                route_meta={"intent": "generate_image", "source": "direct"},
                image={
                    "url": str(img_result["url"]),
                    "prompt": img_prompt,
                    "quality": img_result.get("quality"),
                },
            )
        err = str(img_result.get("error") or "No pude generar la imagen.")
        return _finish(
            f"No pude generar la imagen: {err}",
            route_meta={"intent": "generate_image", "source": "direct_error"},
        )

    pdf_req = parse_pdf_request(text)
    if pdf_req and is_pdf_intent(text):
        from app.deps.plan_access import effective_plan_limits

        limits, reason, _trial = effective_plan_limits(user_id)
        if reason == "trial_expired":
            return _finish(
                "Tu prueba terminó. Elige un plan en Precios o continúa con el plan Básico gratis.",
            )
        if not limits.pdf_reports:
            return _finish(
                "Los PDFs requieren plan Élite o Founding. Mejora tu plan en /pricing.",
            )
        pdf_title, pdf_body = pdf_req
        if pdf_title == "Documento CED" and pdf_body:
            pdf_title = pdf_body[:60].strip()
        artifact = store_pdf(
            user_id=user_id,
            title=pdf_title,
            content=pdf_body,
            conversation_id=conversation_id,
        )
        return _finish(
            f'Listo. PDF "{artifact.title}" generado. Usa el botón Descargar abajo.',
            route_meta={"intent": "generar_pdf", "source": "direct"},
            pdf=_pdf_attachment_from_artifact(artifact),
        )

    followup_prompt = _advanced_confirm_followup(history, text)
    if followup_prompt:
        deep = consultar_sistema_avanzado(followup_prompt)
        if deep.get("ok"):
            reply = str(deep.get("result") or "").strip() or "Listo."
        else:
            reply = str(deep.get("error") or "El sistema avanzado no respondió.")
        return _finish(
            reply,
            route_meta={"intent": "advanced_analysis", "source": "confirm_followup"},
        )

    route = route_message(user_id, text, channel="text")

    if route.intent == "memory_save" and route.speakable:
        return _finish(route.speakable, route_meta=route.to_dict())

    if route.needs_advanced_confirm and route.speakable:
        return _finish(route.speakable, route_meta=route.to_dict())

    if route.intent == "advanced_analysis" and route.speakable:
        return _finish(route.speakable, route_meta=route.to_dict())

    messages = _anthropic_messages(history)
    messages.append({"role": "user", "content": text})
    system = _build_chat_system(user_id, text, route)

    try:
        reply, pdf_attachment, image_attachment = _complete_chat_resilient(
            user_id,
            user_text=text,
            anthropic_key=anthropic_key,
            openai_key=openai_key,
            openai_model=settings.openai_model_chat,
            system=system,
            messages=messages,
        )
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        body = exc.response.text[:300]
        logger.error("[CHAT] provider %s %s", status, body)
        if status in (401, 403):
            raise TextChatError(
                "Servicio de chat temporalmente no disponible. Intenta de nuevo en unos minutos.",
                http_status=503,
            ) from exc
        if status == 404:
            raise TextChatError(
                "Modelo de chat no disponible. Contacta soporte.",
                http_status=503,
            ) from exc
        if status == 429:
            raise TextChatError(
                "Demasiadas solicitudes. Espera un momento e intenta de nuevo.",
                http_status=429,
            ) from exc
        raise TextChatError(
            "No pude obtener respuesta del asistente. Intenta de nuevo en un momento.",
            http_status=503,
        ) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("[CHAT] provider failed")
        raise TextChatError(
            "Error de conexión con el asistente.",
            http_status=503,
        ) from exc

    return _finish(
        reply,
        route_meta=route.to_dict(),
        pdf=pdf_attachment,
        image=image_attachment,
    )
