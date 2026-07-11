"""Servicio principal Modo Avanzado — aislado de Finanzas, Chat Normal y Llama."""

from __future__ import annotations

import concurrent.futures
import json
import logging
import re
import threading
import time
from typing import Any, Callable, Iterator, TypeVar

from app.services.advanced_mode.claude_stream import (
    advanced_is_configured,
    anthropic_simple_reply,
    iter_advanced_claude_stream,
    require_anthropic_api_key,
    stream_max_tokens,
)
from app.services.advanced_mode.constants import (
    ADVANCED_MODEL_LABEL,
    ADVANCED_STREAM_MODEL_LABEL,
    ADVANCED_SYSTEM_PROMPT,
    ADVANCED_STREAM_SYSTEM,
)
from app.services.advanced_mode.intents import needs_advanced_full_pipeline
from app.services.advanced_mode.vision import analyze_image_with_claude
from app.services.system_clock import clock_context_block, try_instant_datetime_reply
from app.services.text_chat import (
    DIRECT_IMAGE_MAX_CHARS,
    _anthropic_messages,
    _chat_image_attachment,
    _complete_chat_with_tools,
    _execute_direct_pdf,
    _finalize_chat_reply,
    _try_direct_pdf_from_context,
    is_generate_image_intent,
    is_pdf_intent,
    parse_followup_image_prompt,
    parse_generate_image_prompt,
    resolve_pdf_request,
)

logger = logging.getLogger(__name__)

_GREETING_ONLY = re.compile(
    r"^(?:hola|hey|hi|hello|buenas?|buenos?\s*d[ií]as?|buenas?\s*tardes?|"
    r"buenas?\s*noches?|qu[eé]\s*tal|saludos)[\s!.?👋😊]*$",
    re.I,
)

_WELCOME_MARKERS = (
    "modo avanzado activo",
    "modo avanzado listo",
    "castillo evolución digital",
    "bienvenido al sistema",
)

_DEDUP_TTL_SEC = 45.0
_dup_lock = threading.Lock()
_dup_cache: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}

_T = TypeVar("_T")
_KEEPALIVE_INTERVAL_SEC = 8.0


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


def history_for_stream(history: list[dict[str, Any]]) -> list[dict[str, str]]:
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


def history_as_chat_rows(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
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


def _stream_system_with_clock() -> str:
    return (
        ADVANCED_STREAM_SYSTEM
        + f"\n\n{clock_context_block()}"
        + "\nPROHIBIDO escribir tool_code, print(), search_web() ni pseudo-código. "
        "Responde en español natural o deja que el backend use herramientas."
    )


def _sse_event(name: str, payload: dict[str, Any]) -> str:
    return f"event: {name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _sse_flush() -> str:
    return ": flush\n\n"


def _dup_lookup(user_id: str, text: str) -> dict[str, Any] | None:
    key = (user_id, text.strip().lower())
    now = time.monotonic()
    with _dup_lock:
        entry = _dup_cache.get(key)
        if entry and now - entry[0] < _DEDUP_TTL_SEC:
            return entry[1]
    return None


def _dup_remember(user_id: str, text: str, payload: dict[str, Any]) -> None:
    key = (user_id, text.strip().lower())
    with _dup_lock:
        _dup_cache[key] = (time.monotonic(), payload)


def _finish_payload(
    *,
    response: str,
    model: str,
    pdf: dict[str, Any] | None = None,
    image: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"response": response, "model": model}
    if pdf:
        payload["pdf"] = pdf
    if image:
        payload["image"] = image
    return payload


def _yield_done_with_text(result: dict[str, Any]) -> Iterator[str]:
    response = str(result.get("response") or "").strip()
    if response:
        yield _sse_event("token", {"text": response})
        yield _sse_flush()
    yield _sse_event("done", result)


def _yield_done_cached(
    user_id: str,
    text: str,
    result: dict[str, Any],
) -> Iterator[str]:
    _dup_remember(user_id, text, result)
    yield from _yield_done_with_text(result)


def _iter_blocking_with_keepalives(
    fn: Callable[[], _T],
    *,
    interval: float = _KEEPALIVE_INTERVAL_SEC,
) -> Iterator[tuple[str, _T | None]]:
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(fn)
        while not fut.done():
            yield ("ping", None)
            try:
                yield ("done", fut.result(timeout=interval))
                return
            except concurrent.futures.TimeoutError:
                continue


def _stream_fallback_reply(
    *,
    stream_system: str,
    stream_messages: list[dict[str, str]],
    text: str,
    max_tokens: int,
    history: list[dict[str, Any]] | None = None,
) -> str:
    api_key = require_anthropic_api_key()
    reply = anthropic_simple_reply(
        api_key=api_key,
        system=stream_system,
        messages=stream_messages,
        max_tokens=max_tokens,
        user_text=text,
    )
    if reply:
        finalized = _finalize_chat_reply(reply.strip())
        if finalized:
            return finalized
    instant = try_instant_datetime_reply(text, history=history)
    if instant:
        return instant
    return (
        "Disculpe señor, no pude completar la respuesta avanzada ahora mismo. "
        "¿Puede repetir su pregunta?"
    )


def _try_direct_image(
    user_id: str,
    text: str,
    history_rows: list[dict[str, Any]],
    conversation_id: str,
) -> dict[str, Any] | None:
    from app.services.chat_image_generation import (
        run_chat_image_generation,
        should_take_direct_image_path,
    )

    if not should_take_direct_image_path(text, history_rows):
        return None

    plan_id = None
    try:
        from app.services import supabase_db

        sub = supabase_db.get_subscription(user_id)
        plan_id = sub.get("plan_id") if sub else None
    except Exception:  # noqa: BLE001
        pass

    gen = run_chat_image_generation(
        user_id,
        conversation_id,
        text,
        history_rows,
        plan_id=plan_id,
    )
    if not gen.get("ok") or not gen.get("url"):
        err = str(gen.get("error") or gen.get("reply") or "No pude generar la imagen.")
        return _finish_payload(response=err, model=ADVANCED_MODEL_LABEL)

    caption = str(gen.get("caption") or "Imagen generada")
    return _finish_payload(
        response=str(gen.get("reply") or "Listo, señor. Aquí está su imagen generada."),
        model=ADVANCED_MODEL_LABEL,
        image=_chat_image_attachment(
            str(gen["url"]),
            caption=caption,
            quality=str(gen.get("quality") or ""),
        ),
    )


def send_advanced_message(
    user_id: str,
    *,
    message: str,
    history: list[dict[str, Any]],
    conversation_id: str | None = None,
) -> dict[str, Any]:
    text = message.strip()
    if not text:
        raise ValueError("Mensaje vacío.")

    instant = _instant_greeting_reply(text) or try_instant_datetime_reply(
        text, history=history
    )
    if instant:
        return _finish_payload(response=instant, model=ADVANCED_STREAM_MODEL_LABEL)

    conv_id = _conversation_id(user_id, conversation_id)
    history_rows = history_as_chat_rows(history)

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

    anthropic_key = require_anthropic_api_key()

    image_result = _try_direct_image(user_id, text, history_rows, conv_id)
    if image_result:
        return image_result

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
        logger.exception("[ADV-MODE] tools chat failed: %s", exc)
        raise

    return _finish_payload(
        response=_finalize_chat_reply(reply),
        model=ADVANCED_MODEL_LABEL,
        pdf=pdf_attachment,
        image=image_attachment,
    )


def send_advanced_message_with_image(
    user_id: str,
    *,
    message: str,
    history: list[dict[str, Any]],
    image_bytes: bytes,
    image_media_type: str,
    image_mode: str = "analyze",
    conversation_id: str | None = None,
) -> dict[str, Any]:
    text = (message or "").strip() or "¿Qué piensas de esta imagen?"
    api_key = require_anthropic_api_key()
    conv_id = _conversation_id(user_id, conversation_id)

    if image_mode in ("variation", "inspired", "edit"):
        from app.services.image_reference_generator import generate_image_with_reference

        style_map = {
            "variation": "variation",
            "inspired": "inspired",
            "edit": "edit",
        }
        prompt = text
        if image_mode == "variation" and "variación" not in text.lower():
            prompt = f"Genera una variación de esta imagen: {text}"
        elif image_mode == "inspired":
            prompt = f"Crea una imagen inspirada en esta referencia: {text}"
        elif image_mode == "edit":
            prompt = f"Edita esta imagen: {text}"

        ref_result = generate_image_with_reference(
            user_id=user_id,
            prompt=prompt,
            reference_image=image_bytes,
            content_type=image_media_type or "image/jpeg",
            style_mode=style_map.get(image_mode, "edit"),
        )
        if ref_result.get("ok") and ref_result.get("url"):
            caption = text[:72] if len(text) <= 72 else "Imagen generada"
            return _finish_payload(
                response="Listo, señor. Aquí está el resultado con su imagen de referencia.",
                model=ADVANCED_MODEL_LABEL,
                image=_chat_image_attachment(
                    str(ref_result["url"]),
                    caption=caption,
                    quality=str(ref_result.get("quality") or ""),
                ),
            )
        err = str(ref_result.get("error") or "No pude procesar la imagen.")
        return _finish_payload(response=err, model=ADVANCED_MODEL_LABEL)

    reply = analyze_image_with_claude(
        api_key=api_key,
        image_bytes=image_bytes,
        media_type=image_media_type or "image/jpeg",
        user_text=text,
    )
    return _finish_payload(
        response=_finalize_chat_reply(reply),
        model=ADVANCED_STREAM_MODEL_LABEL,
    )


def iter_advanced_message_stream(
    user_id: str,
    *,
    message: str,
    history: list[dict[str, Any]],
    conversation_id: str | None = None,
) -> Iterator[str]:
    text = message.strip()
    conv_id = _conversation_id(user_id, conversation_id)
    history_rows = history_as_chat_rows(history)

    instant = _instant_greeting_reply(text) or try_instant_datetime_reply(
        text, history=history
    )
    if instant:
        payload = _finish_payload(response=instant, model=ADVANCED_STREAM_MODEL_LABEL)
        _dup_remember(user_id, text, payload)
        yield _sse_event("token", {"text": instant})
        yield _sse_flush()
        yield _sse_event("done", payload)
        return

    cached = _dup_lookup(user_id, text)
    if cached:
        response = str(cached.get("response") or "").strip()
        if response:
            yield _sse_event("token", {"text": response})
            yield _sse_flush()
        yield _sse_event("done", cached)
        return

    yield _sse_event("status", {"text": "Preparando análisis…"})
    yield _sse_flush()

    anthropic_key = require_anthropic_api_key()

    from app.services.chat_image_generation import should_take_direct_image_path

    # Imagen: ruta directa (Gemini Flash Image) — no pasar por chat con herramientas.
    if should_take_direct_image_path(text, history_rows):
        status = "Generando imagen con IA…"
        yield _sse_event("status", {"text": status})
        yield _sse_flush()

        def _run_image_job() -> dict[str, Any]:
            direct = _try_direct_image(user_id, text, history_rows, conv_id)
            if direct:
                return direct
            return send_advanced_message(
                user_id,
                message=text,
                history=history,
                conversation_id=conv_id,
            )

        result: dict[str, Any] | None = None
        try:
            for kind, payload in _iter_blocking_with_keepalives(_run_image_job):
                if kind == "ping":
                    yield _sse_event("status", {"text": status})
                    yield _sse_flush()
                else:
                    result = payload
        except Exception:  # noqa: BLE001
            logger.exception("[ADV-MODE] image generation failed")
            result = _finish_payload(
                response="Disculpe señor, no pude generar la imagen. Intente de nuevo.",
                model=ADVANCED_MODEL_LABEL,
            )
        if result is None:
            result = _finish_payload(
                response="Disculpe señor, no pude generar la imagen.",
                model=ADVANCED_MODEL_LABEL,
            )
        yield from _yield_done_cached(user_id, text, result)
        return

    if needs_advanced_full_pipeline(text, history_rows):
        status = "Analizando y preparando respuesta…"
        yield _sse_event("status", {"text": status})
        yield _sse_flush()

        def _run_tools_pipeline() -> dict[str, Any]:
            return send_advanced_message(
                user_id,
                message=text,
                history=history,
                conversation_id=conv_id,
            )

        result = None
        try:
            for kind, payload in _iter_blocking_with_keepalives(_run_tools_pipeline):
                if kind == "ping":
                    yield _sse_event("status", {"text": status})
                    yield _sse_flush()
                else:
                    result = payload
        except Exception:  # noqa: BLE001
            logger.exception("[ADV-MODE] tools pipeline failed")
            fallback = try_instant_datetime_reply(text, history=history) or (
                "Disculpe señor, tuve un inconveniente técnico. ¿Puede repetir su pregunta?"
            )
            result = _finish_payload(response=fallback, model=ADVANCED_STREAM_MODEL_LABEL)
        if result is None:
            result = _finish_payload(
                response=(
                    "Disculpe señor, tuve un inconveniente técnico. ¿Puede repetir su pregunta?"
                ),
                model=ADVANCED_STREAM_MODEL_LABEL,
            )
        yield from _yield_done_cached(user_id, text, result)
        return

    stream_messages = [*history_for_stream(history), {"role": "user", "content": text}]
    max_tokens = stream_max_tokens(text)
    stream_system = _stream_system_with_clock()

    accumulated: list[str] = []
    stream_buf = ""
    stream_label = ADVANCED_STREAM_MODEL_LABEL
    try:
        from app.services.stream_delta import stream_piece_delta

        logger.info("[ADV-MODE] stream start user=%s", user_id[:8])
        for piece, model_label in iter_advanced_claude_stream(
            api_key=anthropic_key,
            system=stream_system,
            messages=stream_messages,
            max_tokens=max_tokens,
            user_text=text,
        ):
            stream_label = model_label
            delta = stream_piece_delta(stream_buf, piece)
            if not delta:
                continue
            stream_buf += delta
            accumulated.append(delta)
            yield _sse_event("token", {"text": delta})
    except Exception as exc:  # noqa: BLE001
        logger.warning("[ADV-MODE] stream failed, light fallback: %s", exc)
        fallback_text = _stream_fallback_reply(
            stream_system=stream_system,
            stream_messages=stream_messages,
            text=text,
            max_tokens=max_tokens,
            history=history,
        )
        yield from _yield_done_cached(
            user_id,
            text,
            _finish_payload(response=fallback_text, model=ADVANCED_STREAM_MODEL_LABEL),
        )
        return

    reply = _finalize_chat_reply("".join(accumulated).strip())
    if not reply:
        fallback_text = _stream_fallback_reply(
            stream_system=stream_system,
            stream_messages=stream_messages,
            text=text,
            max_tokens=max_tokens,
            history=history,
        )
        yield from _yield_done_cached(
            user_id,
            text,
            _finish_payload(response=fallback_text, model=stream_label),
        )
        return

    yield from _yield_done_cached(
        user_id,
        text,
        _finish_payload(response=reply, model=stream_label),
    )
