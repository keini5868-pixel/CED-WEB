"""Chat avanzado CED — Claude Sonnet con herramientas (PDF, imágenes, web)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Iterator

import httpx

from app.config import get_settings
from app.services.deliverable_replies import CHAT_DELIVERABLE_RULES
from app.services.system_clock import (
    clock_context_block,
    try_instant_datetime_reply,
)
from app.services.text_chat import (
    CHAT_DELIVERABLE_MAX_TOKENS,
    CHAT_MODEL,
    CHAT_MODEL_FAST,
    DIRECT_IMAGE_MAX_CHARS,
    _anthropic_messages,
    _can_stream_chat_text,
    _chat_image_attachment,
    _gemini_chat_model,
    _gemini_simple_reply_stream,
    _chat_max_tokens,
    _complete_chat_with_tools,
    _execute_direct_pdf,
    _finalize_chat_reply,
    _has_hallucinated_tool,
    _has_hallucinated_tool_code,
    _needs_chat_tools,
    _pdf_attachment_from_artifact,
    _resolve_hallucinated_tool_code_reply,
    _try_direct_pdf_from_context,
    is_generate_image_intent,
    is_pdf_intent,
    parse_followup_image_prompt,
    parse_generate_image_prompt,
    resolve_pdf_request,
)

logger = logging.getLogger(__name__)

# Haiku en streaming conversacional; Sonnet en PDF/planes/herramientas.
ADVANCED_STREAM_MODEL = CHAT_MODEL_FAST
ADVANCED_DEEP_MODEL = CHAT_MODEL
ADVANCED_STREAM_MODEL_LABEL = "claude-haiku"
ADVANCED_DEEP_MODEL_LABEL = "claude-sonnet-4-6"
# Compat — herramientas y PDF usan Sonnet.
ADVANCED_MODEL = ADVANCED_DEEP_MODEL
ADVANCED_MODEL_FALLBACK = ADVANCED_STREAM_MODEL
ADVANCED_MODEL_LABEL = ADVANCED_DEEP_MODEL_LABEL


def _llm_provider_keys() -> tuple[str, str]:
    from app.config import get_settings

    settings = get_settings()
    return settings.anthropic_api_key.strip(), settings.google_api_key.strip()


def advanced_is_configured() -> bool:
    anthropic, google = _llm_provider_keys()
    return bool(anthropic or google)


def _ensure_llm_providers(*, needs_anthropic: bool = False) -> tuple[str, str]:
    from app.services.llama_service import use_llama

    anthropic, google = _llm_provider_keys()
    if needs_anthropic and not anthropic:
        raise ValueError("missing_anthropic_api_key")
    if not anthropic and not google and not use_llama():
        raise ValueError("missing_llm_api_key")
    return anthropic, google

ADVANCED_SYSTEM_PROMPT = f"""Eres el sistema AVANZADO de CED — Castillo Evolución Digital.
Analista experto en negocios, marketing digital, ventas, estrategia empresarial y tecnología.

Das análisis profundos, detallados y accionables: estrategias completas, planes ejecutables y soluciones reales.
Responde en español latinoamericano, profesional pero cercano. Trata al usuario como "señor" o por su nombre.

CAPACIDADES (usa las herramientas cuando corresponda):
- search_web: información actual (noticias, clima, datos recientes).
- generar_pdf: documentos PDF descargables (content = texto completo del documento).
- generate_image: crear imágenes y creativos publicitarios.
- publicar_facebook / publicar_instagram: si el usuario conectó redes Meta.
- NUNCA escribas URLs /v1/pdf/download; la app muestra el botón Descargar.
- NUNCA digas "voy a buscar" sin invocar search_web en el mismo turno.

{CHAT_DELIVERABLE_RULES}
"""

# Prompt corto — streaming conversacional (menos latencia).
ADVANCED_STREAM_SYSTEM = """Eres CED modo avanzado: negocios, marketing, ventas y estrategia.
Español latinoamericano, profesional y cercano. Trata al usuario como "señor".
REGLAS DE BREVEDAD:
- Saludo o mensaje corto → 1-2 frases máximo, sin repetir bienvenida ni listar capacidades.
- Pregunta simple → un párrafo directo.
- Solo desarrolla en profundidad si piden análisis, estrategia, plan o PDF.
- Máximo 1 emoji por respuesta, solo si aporta.
"""

_GREETING_ONLY = re.compile(
    r"^(?:hola|hey|hi|hello|buenas?|buenos?\s*d[ií]as?|buenas?\s*tardes?|"
    r"buenas?\s*noches?|qu[eé]\s*tal|saludos)[\s!.?👋😊]*$",
    re.I,
)

_WELCOME_MARKERS = (
    "modo avanzado activo",
    "castillo evolución digital",
    "bienvenido al sistema",
)


def _try_instant_datetime_reply(
    text: str,
    *,
    history: list[dict[str, Any]] | None = None,
) -> str | None:
    return try_instant_datetime_reply(text, history=history)


def _advanced_stream_system_with_clock() -> str:
    return (
        ADVANCED_STREAM_SYSTEM
        + f"\n\n{clock_context_block()}"
        + "\nPROHIBIDO escribir tool_code, print(), search_web() ni pseudo-código. "
        "Responde en español natural o deja que el backend use herramientas."
    )


def _needs_advanced_tools(text: str, history_rows: list[dict[str, Any]]) -> bool:
    """Misma cobertura que chat normal: no hacer stream sin tools si hace falta acción real."""
    if _needs_chat_tools(text):
        return True
    if is_pdf_intent(text) or is_generate_image_intent(text):
        return True
    if resolve_pdf_request(text, history_rows):
        return True
    if not _can_stream_chat_text(text):
        return True
    return False


def _recover_advanced_reply(
    user_id: str,
    reply: str,
    *,
    text: str,
    history: list[dict[str, Any]],
    conversation_id: str,
) -> str:
    """Corrige tool_code alucinado o promesas de búsqueda sin ejecutar herramienta."""
    cleaned = _finalize_chat_reply((reply or "").strip())
    if not cleaned:
        return cleaned

    if not _has_hallucinated_tool_code(cleaned) and not _has_hallucinated_tool(cleaned):
        return cleaned

    history_rows = _history_as_chat_rows(history)
    messages = _anthropic_messages(history_rows)
    messages.append({"role": "user", "content": text})

    fixed = _resolve_hallucinated_tool_code_reply(
        cleaned,
        messages,
        user_id=user_id,
        user_text=text,
    )
    if fixed and not _has_hallucinated_tool_code(fixed):
        return _finalize_chat_reply(fixed)

    instant = _try_instant_datetime_reply(text, history=history)
    if instant:
        return instant

    logger.warning("[ADVANCED] tool_code en stream — escalando a pipeline con herramientas")
    result = send_advanced_message(
        user_id,
        message=text,
        history=history,
        conversation_id=conversation_id,
    )
    return str(result.get("response") or cleaned)


def _instant_greeting_reply(text: str) -> str | None:
    if _GREETING_ONLY.match(text.strip()):
        return (
            "Hola, señor. Modo avanzado listo — ¿qué negocio o proyecto quiere analizar hoy?"
        )
    return None


def _is_welcome_boilerplate(content: str) -> bool:
    lowered = content.strip().lower()
    if len(lowered) < 20:
        return False
    return any(marker in lowered for marker in _WELCOME_MARKERS)


def _history_for_stream(history: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Historial sin mensajes de bienvenida del UI — evita respuestas largas repetidas."""
    messages: list[dict[str, str]] = []
    for turn in history[-12:]:
        role = str(turn.get("role") or "").strip().lower()
        content = str(turn.get("content") or "").strip()
        if not content or _is_welcome_boilerplate(content):
            continue
        if role in ("user", "human"):
            messages.append({"role": "user", "content": content})
        elif role in ("assistant", "model", "claude"):
            messages.append({"role": "assistant", "content": content})
    return messages[-10:]


def _stream_max_tokens(text: str) -> int:
    length = len(text.strip())
    if length < 50:
        return 280
    if length < 180:
        return 700
    if _needs_sonnet_stream(text):
        return _chat_max_tokens(text)
    return min(1200, _chat_max_tokens(text))


def _stream_system_prompt(text: str) -> str:
    if len(text.strip()) < 50:
        return ADVANCED_STREAM_SYSTEM
    return ADVANCED_STREAM_SYSTEM + (
        "\nDesarrolla con detalle solo si el usuario lo pide explícitamente."
    )


def _needs_sonnet_stream(text: str) -> bool:
    """Planes largos / entregables → Sonnet aunque sea streaming."""
    from app.services.text_chat import _is_deliverable_request

    if len(text.strip()) > 420:
        return True
    if _is_deliverable_request(text):
        return True
    return bool(
        re.search(
            r"estrategia\s+completa|plan\s+de\s+negocio|an[aá]lisis\s+profundo|"
            r"informe\s+detallado|roadmap|plan\s+maestro|plan\s+ejecutivo",
            text,
            re.I,
        )
    )


def _pick_stream_model(text: str) -> tuple[str, str]:
    if _needs_sonnet_stream(text):
        return ADVANCED_DEEP_MODEL, ADVANCED_DEEP_MODEL_LABEL
    return ADVANCED_STREAM_MODEL, ADVANCED_STREAM_MODEL_LABEL


def _normalize_history(history: list[dict[str, Any]]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for turn in history[-20:]:
        role = str(turn.get("role") or "").strip().lower()
        content = str(turn.get("content") or "").strip()
        if not content:
            continue
        if role in ("user", "human"):
            messages.append({"role": "user", "content": content})
        elif role in ("assistant", "model", "claude"):
            messages.append({"role": "assistant", "content": content})
    return messages


def _history_as_chat_rows(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for turn in history[-20:]:
        role = str(turn.get("role") or "").strip().lower()
        content = str(turn.get("content") or "").strip()
        if not content:
            continue
        if role in ("user", "human"):
            rows.append({"role": "user", "content": content})
        elif role in ("assistant", "model", "claude"):
            rows.append({"role": "model", "content": content})
    return rows


def _conversation_id(user_id: str, explicit: str | None) -> str:
    return explicit or f"advanced-{user_id}"


def _sse_event(name: str, payload: dict[str, Any]) -> str:
    return f"event: {name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _finish_payload(
    *,
    response: str,
    model: str,
    pdf: dict[str, Any] | None = None,
    image: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "response": response,
        "model": model,
    }
    if pdf:
        payload["pdf"] = pdf
    if image:
        payload["image"] = image
    return payload


def _try_direct_image(
    user_id: str,
    text: str,
    history_rows: list[dict[str, Any]],
    conversation_id: str,
) -> dict[str, Any] | None:
    from app.services.chat_intents import is_pdf_intent, mentions_pdf

    if is_pdf_intent(text) or mentions_pdf(text):
        return None
    img_prompt = parse_generate_image_prompt(text)
    followup = (
        parse_followup_image_prompt(text, history_rows)
        if not img_prompt
        else None
    )
    effective = img_prompt or followup
    if not effective or not is_generate_image_intent(text) or len(text) > DIRECT_IMAGE_MAX_CHARS:
        return None
    if _needs_chat_tools(text) and not img_prompt:
        return None

    from app.services.gemini_images import generate_image
    from app.services.marketing_creative import (
        build_display_label,
        extract_product_subject,
        is_marketing_creative_intent,
        resolve_image_creation_from_text,
    )
    from app.services.publish_image_context import register_text_chat_image_url
    from app.services.text_chat import _recent_chat_context

    plan_id = None
    try:
        from app.services import supabase_db

        sub = supabase_db.get_subscription(user_id)
        plan_id = sub.get("plan_id") if sub else None
    except Exception:  # noqa: BLE001
        pass

    chat_context = _recent_chat_context(history_rows)
    creation = resolve_image_creation_from_text(text, history_rows)
    display_label = ""
    success_reply = "Listo. Aquí está su imagen generada."
    if creation:
        img_result = generate_image(
            user_id=user_id,
            plan_id=plan_id,
            prompt=creation["internal_prompt"],
            quality="auto",
            context="",
            display_label=creation["display_label"],
        )
        success_reply = creation.get("reply") or success_reply
        display_label = creation["display_label"]
    else:
        if is_marketing_creative_intent(text):
            display_label = build_display_label(extract_product_subject(chat_context))
            success_reply = "Listo, señor. Aquí está su creativo publicitario."
        img_result = generate_image(
            user_id=user_id,
            plan_id=plan_id,
            prompt=effective,
            quality="auto",
            context=chat_context,
            display_label=display_label or None,
        )

    if not img_result.get("ok") or not img_result.get("url"):
        err = str(img_result.get("error") or "No pude generar la imagen.")
        return _finish_payload(response=err, model=ADVANCED_MODEL_LABEL)

    register_text_chat_image_url(user_id, conversation_id, str(img_result["url"]))
    caption = str(img_result.get("caption") or display_label or "Imagen generada")
    return _finish_payload(
        response=success_reply,
        model=ADVANCED_MODEL_LABEL,
        image=_chat_image_attachment(
            str(img_result["url"]),
            caption=caption,
            quality=str(img_result.get("quality") or ""),
        ),
    )


def send_advanced_message(
    user_id: str,
    *,
    message: str,
    history: list[dict[str, Any]],
    conversation_id: str | None = None,
) -> dict[str, Any]:
    """Chat avanzado completo — herramientas + PDF + imágenes."""
    text = message.strip()
    if not text:
        raise ValueError("Mensaje vacío.")

    instant = _instant_greeting_reply(text) or _try_instant_datetime_reply(
        text,
        history=history,
    )
    if instant:
        return _finish_payload(
            response=instant,
            model=ADVANCED_STREAM_MODEL_LABEL,
        )

    anthropic_key, google_key = _ensure_llm_providers(needs_anthropic=True)

    conv_id = _conversation_id(user_id, conversation_id)
    history_rows = _history_as_chat_rows(history)

    direct_pdf = _try_direct_pdf_from_context(
        user_id,
        text=text,
        history=history_rows,
        conversation_id=conv_id,
    )
    if direct_pdf:
        reply, attachment = direct_pdf
        return _finish_payload(
            response=_finalize_chat_reply(reply),
            model=ADVANCED_MODEL_LABEL,
            pdf=attachment if attachment.get("file_id") else None,
        )

    pdf_req = resolve_pdf_request(text, history_rows)
    if pdf_req and is_pdf_intent(text):
        title, body = pdf_req
        pdf_result = _execute_direct_pdf(
            user_id,
            title=title,
            content=body,
            history=history_rows,
            conversation_id=conv_id,
            user_request=text,
        )
        if pdf_result:
            reply, attachment = pdf_result
            return _finish_payload(
                response=_finalize_chat_reply(reply),
                model=ADVANCED_MODEL_LABEL,
                pdf=attachment if attachment.get("file_id") else None,
            )

    image_result = _try_direct_image(user_id, text, history_rows, conv_id)
    if image_result:
        return image_result

    normalized = _normalize_history(history)
    messages = [*normalized, {"role": "user", "content": text}]
    anthropic_messages = _anthropic_messages(history_rows)
    anthropic_messages.append({"role": "user", "content": text})

    try:
        reply, pdf_attachment, image_attachment = _complete_chat_with_tools(
            user_id,
            api_key=anthropic_key,
            system=ADVANCED_SYSTEM_PROMPT,
            messages=anthropic_messages,
            conversation_id=conv_id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("[ADVANCED] tools chat failed: %s", exc)
        raise

    return _finish_payload(
        response=_finalize_chat_reply(reply),
        model=ADVANCED_MODEL_LABEL,
        pdf=pdf_attachment,
        image=image_attachment,
    )


def _iter_anthropic_text_stream(
    *,
    api_key: str,
    system: str,
    messages: list[dict[str, Any]],
    max_tokens: int,
    user_text: str,
) -> Iterator[tuple[str, str]]:
    """Yield (text_chunk, model_label)."""
    primary, label = _pick_stream_model(user_text)
    fallback = (
        ADVANCED_STREAM_MODEL
        if primary == ADVANCED_DEEP_MODEL
        else ADVANCED_DEEP_MODEL
    )
    last_exc: Exception | None = None
    for model in (primary, fallback):
        try:
            for piece in _stream_model_text(
                api_key=api_key,
                system=system,
                messages=messages,
                max_tokens=max_tokens,
                model=model,
            ):
                model_label = label if model == primary else (
                    ADVANCED_DEEP_MODEL_LABEL
                    if model == ADVANCED_DEEP_MODEL
                    else ADVANCED_STREAM_MODEL_LABEL
                )
                yield piece, model_label
            return
        except httpx.HTTPStatusError as exc:
            last_exc = exc
            if exc.response.status_code in (400, 404) and model != fallback:
                logger.warning("[ADVANCED] stream model %s unavailable, fallback", model)
                continue
            raise
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if model != fallback:
                continue
            raise
    if last_exc:
        raise last_exc


def _stream_model_text(
    *,
    api_key: str,
    system: str,
    messages: list[dict[str, Any]],
    max_tokens: int,
    model: str,
) -> Iterator[str]:
    with httpx.Client(timeout=120.0) as client:
        with client.stream(
            "POST",
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": max_tokens,
                "temperature": 0.25,
                "system": system,
                "messages": messages,
                "stream": True,
            },
        ) as res:
            res.raise_for_status()
            for raw_line in res.iter_lines():
                if not raw_line or not raw_line.startswith("data: "):
                    continue
                chunk = raw_line[6:].strip()
                if chunk == "[DONE]":
                    break
                try:
                    data = json.loads(chunk)
                except json.JSONDecodeError:
                    continue
                if data.get("type") == "content_block_delta":
                    delta = data.get("delta") or {}
                    if delta.get("type") == "text_delta":
                        piece = str(delta.get("text") or "")
                        if piece:
                            yield piece


def iter_advanced_message_stream(
    user_id: str,
    *,
    message: str,
    history: list[dict[str, Any]],
    conversation_id: str | None = None,
) -> Iterator[str]:
    """SSE — streaming para respuestas conversacionales; herramientas vía respuesta completa."""
    text = message.strip()
    conv_id = _conversation_id(user_id, conversation_id)
    history_rows = _history_as_chat_rows(history)

    instant = _instant_greeting_reply(text) or _try_instant_datetime_reply(
        text,
        history=history,
    )
    if instant:
        yield _sse_event("token", {"text": instant})
        yield _sse_event("done", _finish_payload(
            response=instant,
            model=ADVANCED_STREAM_MODEL_LABEL,
        ))
        return

    anthropic_key, google_key = _ensure_llm_providers(needs_anthropic=False)

    # PDF / imagen / herramientas / web en vivo → respuesta completa (no stream parcial).
    needs_tools = _needs_advanced_tools(text, history_rows)

    if needs_tools:
        yield _sse_event("status", {"text": "Analizando y preparando respuesta…"})
        try:
            result = send_advanced_message(
                user_id,
                message=text,
                history=history,
                conversation_id=conv_id,
            )
        except Exception:  # noqa: BLE001
            logger.exception("[ADVANCED] tools pipeline failed")
            fallback = _try_instant_datetime_reply(text, history=history) or (
                "Disculpe señor, tuve un inconveniente técnico. ¿Puede repetir su pregunta?"
            )
            result = _finish_payload(
                response=fallback,
                model=ADVANCED_STREAM_MODEL_LABEL,
            )
        yield _sse_event("done", result)
        return

    normalized = _history_for_stream(history)
    stream_messages = [*normalized, {"role": "user", "content": text}]
    max_tokens = _stream_max_tokens(text)
    stream_system = _advanced_stream_system_with_clock()

    accumulated: list[str] = []
    stream_label = ADVANCED_STREAM_MODEL_LABEL
    try:
        # Chat Avanzado: Claude primero (rápido); Gemini como respaldo.
        if anthropic_key and not _needs_sonnet_stream(text):
            for piece, model_label in _iter_anthropic_text_stream(
                api_key=anthropic_key,
                system=stream_system,
                messages=stream_messages,
                max_tokens=max_tokens,
                user_text=text,
            ):
                stream_label = model_label
                accumulated.append(piece)
                yield _sse_event("token", {"text": piece})
        elif google_key and not _needs_sonnet_stream(text):
            stream_label = "gemini-2.5-flash"
            for piece in _gemini_simple_reply_stream(
                api_key=google_key,
                model=_gemini_chat_model(),
                system=stream_system,
                messages=stream_messages,
                max_tokens=max_tokens,
                allow_llama=False,
            ):
                accumulated.append(piece)
                yield _sse_event("token", {"text": piece})
        elif anthropic_key:
            for piece, model_label in _iter_anthropic_text_stream(
                api_key=anthropic_key,
                system=stream_system,
                messages=stream_messages,
                max_tokens=max_tokens,
                user_text=text,
            ):
                stream_label = model_label
                accumulated.append(piece)
                yield _sse_event("token", {"text": piece})
        else:
            raise ValueError("missing_llm_api_key")
    except Exception as exc:  # noqa: BLE001
        logger.warning("[ADVANCED] stream failed, fallback full: %s", exc)
        result = send_advanced_message(
            user_id,
            message=text,
            history=history,
            conversation_id=conv_id,
        )
        yield _sse_event("done", result)
        return

    reply = _recover_advanced_reply(
        user_id,
        "".join(accumulated).strip(),
        text=text,
        history=history,
        conversation_id=conv_id,
    )
    if not reply:
        from app.services.cloud_llm_fallback import chat_cloud_reply

        cloud = chat_cloud_reply(
            system=stream_system,
            messages=stream_messages,
            user_text=text,
            max_tokens=max_tokens,
        )
        if cloud:
            reply = _finalize_chat_reply(cloud)
    if not reply:
        result = send_advanced_message(
            user_id,
            message=text,
            history=history,
            conversation_id=conv_id,
        )
        yield _sse_event("done", result)
        return

    yield _sse_event(
        "done",
        _finish_payload(response=reply, model=stream_label),
    )


# Compatibilidad con tests / imports antiguos
async def claude_advanced_chat(
    message: str,
    history: list[dict[str, Any]],
    user_id: str,
) -> tuple[str, str]:
    result = send_advanced_message(user_id, message=message, history=history)
    return str(result.get("response") or ""), str(result.get("model") or ADVANCED_MODEL_LABEL)
