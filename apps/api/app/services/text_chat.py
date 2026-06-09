"""Chat de texto con Claude — límites por plan + herramientas Meta."""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timezone
from typing import Any

import httpx

from app.config import get_settings
from app.domain.plans import get_plan_limits, normalize_plan_id
from app.services import supabase_db
from app.services.cognitive_router import build_chat_system_extras, route_message
from app.domain.ced_identity import CED_CREATOR_IDENTITY, CED_HUMAN_VOICE_STYLE
from app.services.meta_social import MetaSocialError, publish_facebook, publish_instagram
from app.services.pdf_report import store_pdf

logger = logging.getLogger(__name__)

CHAT_MODEL = "claude-sonnet-4-6"

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
]

CHAT_SYSTEM_BASE = f"""Eres CED (Castillo de la Evolución Digital), asistente dentro de la plataforma CED Web.
Español latinoamericano natural, cálido y directo. NO uses "señor/señora" ni tono de mayordomo.
Responde con markdown cuando ayude. Sé útil y conciso. Nunca menciones Claude, Gemini ni APIs internas.

{CED_CREATOR_IDENTITY}

{CED_HUMAN_VOICE_STYLE}

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
- NUNCA escribas URLs /v1/pdf/download en tu respuesta. Di que el PDF está listo; la app muestra el botón Descargar automáticamente.

PROHIBIDO (respuestas de chatbot genérico):
- "No tengo acceso a internet en tiempo real" — CED tiene búsqueda y herramientas en voz; en chat puedes preparar contenido y publicar vía Meta.
- "No me puedo conectar a tus cuentas" — sí puedes vía Meta OAuth cuando está conectado.
- Recomendar Buffer/Hootsuite como única opción si el usuario ya tiene CED con redes conectadas.

Cuando prepares contenido para redes, entrégalo listo y ofrece publicarlo con CED si aplica."""


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
            )
            return json.dumps(result)
        if name == "publicar_instagram":
            result = publish_instagram(
                user_id,
                str(tool_input.get("caption") or ""),
                image_url=str(tool_input.get("image_url") or ""),
            )
            return json.dumps(result)
        if name == "generar_pdf":
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
) -> dict[str, Any]:
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
                "system": system,
                "messages": messages,
                "tools": CHAT_TOOLS,
            },
        )
        res.raise_for_status()
        return res.json()


def _final_text_from_response(data: dict[str, Any]) -> str:
    blocks = data.get("content") or []
    return "".join(
        b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text"
    ).strip()


def _strip_pdf_markdown_links(text: str) -> str:
    cleaned = re.sub(
        r"\[([^\]]*)\]\(/v1/pdf/download/[a-f0-9]+\)",
        "",
        text,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"https?://[^\s)]+/v1/pdf/download/[a-f0-9]+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"/v1/pdf/download/[a-f0-9]+", "", cleaned, flags=re.IGNORECASE)
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


def _complete_chat_with_tools(
    user_id: str,
    *,
    api_key: str,
    system: str,
    messages: list[dict[str, Any]],
) -> tuple[str, dict[str, Any] | None]:
    pdf_attachment: dict[str, Any] | None = None
    for _ in range(4):
        data = _anthropic_request(api_key=api_key, system=system, messages=messages)
        blocks = data.get("content") or []
        tool_uses = [b for b in blocks if isinstance(b, dict) and b.get("type") == "tool_use"]
        if not tool_uses:
            reply = _final_text_from_response(data)
            if reply:
                if pdf_attachment:
                    reply = _strip_pdf_markdown_links(reply)
                return reply, pdf_attachment
            raise TextChatError("Respuesta vacía del asistente.")

        messages.append({"role": "assistant", "content": blocks})
        tool_results: list[dict[str, Any]] = []
        for tool in tool_uses:
            tool_input = tool.get("input") if isinstance(tool.get("input"), dict) else {}
            result = _run_chat_tool(user_id, str(tool.get("name") or ""), tool_input)
            maybe_pdf = _extract_pdf_from_tool_result(result)
            if maybe_pdf:
                pdf_attachment = maybe_pdf
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tool.get("id"),
                    "content": result,
                }
            )
        messages.append({"role": "user", "content": tool_results})

    raise TextChatError("Demasiados pasos de herramientas. Intenta con un pedido más simple.")


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

    route = route_message(user_id, text, channel="text")

    def _finish(
        reply: str,
        *,
        route_meta: dict | None = None,
        pdf: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        supabase_db.append_message(conversation_id, user_id, "model", reply)
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
        return out

    if route.intent == "memory_save" and route.speakable:
        return _finish(route.speakable, route_meta=route.to_dict())

    if route.needs_advanced_confirm and route.speakable:
        return _finish(route.speakable, route_meta=route.to_dict())

    if route.intent == "advanced_analysis" and route.speakable:
        return _finish(route.speakable, route_meta=route.to_dict())

    messages = _anthropic_messages(history)
    messages.append({"role": "user", "content": text})
    system = _chat_system_for_user(user_id) + "\n\n" + build_chat_system_extras(user_id, route)

    try:
        reply, pdf_attachment = _complete_chat_with_tools(
            user_id,
            api_key=api_key,
            system=system,
            messages=messages,
        )
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

    return _finish(reply, route_meta=route.to_dict(), pdf=pdf_attachment)
