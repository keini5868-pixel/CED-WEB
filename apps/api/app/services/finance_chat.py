"""Chat dedicado de Finanzas Personales — reutiliza el pipeline de chat de CED."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Iterator

from app.modules.finance_module import (
    handle_finance_query_sync,
    is_finance_pending_query,
    is_finance_pending_write,
    is_finance_query_intent,
    is_finance_write_intent,
)
from app.services.claude_advanced import (
    _ensure_llm_providers,
    _history_as_chat_rows,
    _history_for_stream,
    _iter_anthropic_text_stream,
    _stream_max_tokens,
)
from app.services.deliverable_replies import CHAT_DELIVERABLE_RULES
from app.services.finance_ledger import (
    canonical_period,
    format_pending_spoken,
    format_summary_spoken,
    list_pending_payments,
    summarize_finances,
)
from app.services.system_clock import clock_context_block, try_instant_datetime_reply
from app.services.text_chat import (
    _anthropic_messages,
    _complete_chat_with_tools,
    _execute_direct_pdf,
    _finalize_chat_reply,
    _gemini_chat_model,
    _gemini_simple_reply_stream,
    _needs_chat_tools,
    is_pdf_intent,
    resolve_pdf_request,
)

logger = logging.getLogger(__name__)

FINANCE_MODEL_LABEL = "ced-finance"
FINANCE_STREAM_MODEL_LABEL = "gemini-2.5-flash"


def _stream_model_label() -> str:
    from app.services.llama_service import llama_model, use_llama

    if use_llama():
        return llama_model()
    return FINANCE_STREAM_MODEL_LABEL

FINANCE_SYSTEM_PROMPT = f"""Eres CED — Castillo Evolución Digital — en su módulo de FINANZAS PERSONALES.
Eres el mismo CED de siempre: profesional, cercano y directo. Tratas al usuario como "señor" o por su nombre.
Hablas español latinoamericano.

TU ROL EN FINANZAS:
- Ayudas a registrar gastos e ingresos, analizar el historial y crear planes de ahorro realistas.
- También registras PAGOS PENDIENTES (compromisos a futuro, ej. "el lunes tengo que pagar 850")
  con su fecha de vencimiento, para recordárselos al usuario.
- SIEMPRE basas tus análisis y consejos en los DATOS REALES del usuario que se te proveen abajo.
- NUNCA inventes cifras. Si no hay datos suficientes, dilo y pide registrar movimientos.
- Cuando el usuario declare un gasto/ingreso (ej. "gasté 50 en materiales"), confirma que quedó registrado.
- Para consejos: sé concreto y accionable (montos, categorías a recortar, metas mensuales).

CAPACIDADES (usa herramientas cuando corresponda):
- generar_pdf: si piden un plan o reporte financiero descargable (content = documento completo).
- search_web: solo si piden datos externos actuales (tasas, precios).
- NUNCA escribas URLs de descarga; la app muestra el botón Descargar.

{CHAT_DELIVERABLE_RULES}
"""

FINANCE_STREAM_SYSTEM = """Eres CED en modo Finanzas Personales: registro de gastos/ingresos, análisis y ahorro.
Español latinoamericano, profesional y cercano. Trata al usuario como "señor".
REGLAS:
- Básate SIEMPRE en los datos reales del usuario provistos abajo; nunca inventes cifras.
- Respuesta breve y directa; desarrolla en detalle solo si piden un plan o análisis.
- Máximo 1 emoji, solo si aporta.
"""

_GREETING_ONLY = re.compile(
    r"^(?:hola|hey|hi|buenas?|buenos?\s*d[ií]as?|buenas?\s*tardes?|"
    r"buenas?\s*noches?|qu[eé]\s*tal|saludos)[\s!.?👋😊]*$",
    re.I,
)


def _conversation_id(user_id: str, explicit: str | None) -> str:
    return explicit or f"finance-{user_id}"


def _sse_event(name: str, payload: dict[str, Any]) -> str:
    return f"event: {name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _sse_flush() -> str:
    return ": flush\n\n"


def _finish_payload(
    *,
    response: str,
    model: str,
    pdf: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"response": response, "model": model}
    if pdf:
        payload["pdf"] = pdf
    return payload


def _greeting_reply(text: str) -> str | None:
    if _GREETING_ONLY.match(text.strip()):
        return (
            "Hola, señor. Estamos en sus finanzas. "
            "Dígame un gasto o ingreso para anotarlo, o pregúnteme cómo va este mes."
        )
    return None


def _instant_finance_query_reply(user_id: str, text: str) -> str | None:
    """Resumen determinista de finanzas — evita colgar el chat en consultas simples."""
    if not is_finance_query_intent(text) or is_pdf_intent(text):
        return None
    lowered = text.strip().lower()
    period = "mes_pasado" if re.search(r"mes\s+pasado|mes\s+anterior", lowered) else "mes"
    try:
        summary = summarize_finances(user_id, period=canonical_period(period))
        spoken = format_summary_spoken(summary)
        if spoken.strip():
            return spoken
    except Exception:  # noqa: BLE001
        logger.exception("[FINANCE] instant query failed user=%s", user_id[:8])
    return None


def _yield_done_with_text(result: dict[str, Any]) -> Iterator[str]:
    response = str(result.get("response") or "").strip()
    if response:
        yield _sse_event("token", {"text": response})
        yield _sse_flush()
    yield _sse_event("done", result)


def _finance_llm_reply(
    user_id: str,
    *,
    text: str,
    history_rows: list[dict[str, Any]],
    history: list[dict[str, Any]],
    system: str,
    anthropic_key: str,
    google_key: str,
) -> tuple[str, str]:
    """Respuesta LLM para finanzas sin pipeline bloqueante de herramientas."""
    stream_messages = [*_history_for_stream(history), {"role": "user", "content": text}]
    max_tokens = _stream_max_tokens(text)
    accumulated: list[str] = []
    stream_label = _stream_model_label()

    from app.services.llama_service import use_llama

    if google_key or use_llama():
        for piece in _gemini_simple_reply_stream(
            api_key=google_key,
            model=_gemini_chat_model(),
            system=system,
            messages=stream_messages,
            max_tokens=max_tokens,
        ):
            accumulated.append(piece)
    elif anthropic_key:
        for piece, model_label in _iter_anthropic_text_stream(
            api_key=anthropic_key,
            system=system,
            messages=stream_messages,
            max_tokens=max_tokens,
            user_text=text,
        ):
            stream_label = model_label
            accumulated.append(piece)

    reply = _finalize_chat_reply("".join(accumulated).strip())
    if not reply:
        from app.services.cloud_llm_fallback import chat_cloud_reply

        cloud = chat_cloud_reply(
            system=system,
            messages=stream_messages,
            user_text=text,
            max_tokens=max_tokens,
        )
        if cloud:
            reply = _finalize_chat_reply(cloud)
    if not reply:
        instant = _instant_finance_query_reply(user_id, text)
        if instant:
            reply = instant
    if not reply:
        summary = summarize_finances(user_id, period=canonical_period("mes"))
        reply = format_summary_spoken(summary)
    return reply, stream_label


def _finance_snapshot(user_id: str) -> str:
    """Resumen compacto de datos reales para inyectar al modelo."""
    try:
        this_month = summarize_finances(user_id, period="mes")
        last_month = summarize_finances(user_id, period="mes_pasado")
    except Exception:  # noqa: BLE001
        return ""
    lines = ["DATOS REALES DEL USUARIO (no inventes otros):"]
    lines.append("- " + format_summary_spoken(this_month))
    if last_month.get("count"):
        lines.append("- Mes pasado: " + format_summary_spoken(last_month))
    try:
        pending = list_pending_payments(user_id)
        if pending:
            lines.append("- Pagos pendientes: " + format_pending_spoken(pending))
    except Exception:  # noqa: BLE001
        pass
    return "\n".join(lines)


def _finance_system_with_data(base: str, user_id: str) -> str:
    snapshot = _finance_snapshot(user_id)
    parts = [base, clock_context_block()]
    if snapshot:
        parts.append(snapshot)
    return "\n\n".join(parts)


def _needs_finance_tools(text: str, history_rows: list[dict[str, Any]]) -> bool:
    if is_pdf_intent(text):
        return True
    if resolve_pdf_request(text, history_rows):
        return True
    if _needs_chat_tools(text):
        return True
    return False


def _register_movement(user_id: str, text: str) -> dict[str, Any]:
    result = handle_finance_query_sync(user_id, text)
    return _finish_payload(
        response=_finalize_chat_reply(str(result.get("spoken") or "")),
        model=FINANCE_MODEL_LABEL,
    )


def send_finance_message(
    user_id: str,
    *,
    message: str,
    history: list[dict[str, Any]],
    conversation_id: str | None = None,
) -> dict[str, Any]:
    text = message.strip()
    if not text:
        raise ValueError("Mensaje vacío.")

    greeting = _greeting_reply(text) or try_instant_datetime_reply(text, history=history)
    if greeting:
        return _finish_payload(response=greeting, model=_stream_model_label())

    instant_query = _instant_finance_query_reply(user_id, text)
    if instant_query:
        return _finish_payload(response=instant_query, model=_stream_model_label())

    # Registro directo y determinista de un movimiento o pago pendiente.
    if (
        is_finance_write_intent(text)
        or is_finance_pending_write(text)
        or is_finance_pending_query(text)
    ):
        return _register_movement(user_id, text)

    anthropic_key, google_key = _ensure_llm_providers(needs_anthropic=False)
    conv_id = _conversation_id(user_id, conversation_id)
    history_rows = _history_as_chat_rows(history)

    # PDF de plan/reporte financiero.
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
                model=FINANCE_MODEL_LABEL,
                pdf=attachment if attachment.get("file_id") else None,
            )

    system = _finance_system_with_data(FINANCE_SYSTEM_PROMPT, user_id)

    if _needs_finance_tools(text, history_rows):
        if anthropic_key:
            messages = _anthropic_messages(history_rows)
            messages.append({"role": "user", "content": text})
            reply, pdf_attachment, _image = _complete_chat_with_tools(
                user_id,
                api_key=anthropic_key,
                system=system,
                messages=messages,
                conversation_id=conv_id,
            )
            return _finish_payload(
                response=_finalize_chat_reply(reply),
                model=FINANCE_MODEL_LABEL,
                pdf=pdf_attachment,
            )
        reply, model_label = _finance_llm_reply(
            user_id,
            text=text,
            history_rows=history_rows,
            history=history,
            system=system,
            anthropic_key=anthropic_key,
            google_key=google_key,
        )
        return _finish_payload(response=reply, model=model_label)

    reply, model_label = _finance_llm_reply(
        user_id,
        text=text,
        history_rows=history_rows,
        history=history,
        system=_finance_system_with_data(FINANCE_STREAM_SYSTEM, user_id),
        anthropic_key=anthropic_key,
        google_key=google_key,
    )
    return _finish_payload(response=reply, model=model_label)


def iter_finance_message_stream(
    user_id: str,
    *,
    message: str,
    history: list[dict[str, Any]],
    conversation_id: str | None = None,
) -> Iterator[str]:
    text = message.strip()
    conv_id = _conversation_id(user_id, conversation_id)
    history_rows = _history_as_chat_rows(history)

    greeting = _greeting_reply(text) or try_instant_datetime_reply(text, history=history)
    if greeting:
        yield _sse_event("token", {"text": greeting})
        yield _sse_flush()
        yield _sse_event(
            "done", _finish_payload(response=greeting, model=_stream_model_label())
        )
        return

    instant_query = _instant_finance_query_reply(user_id, text)
    if instant_query:
        yield _sse_event("token", {"text": instant_query})
        yield _sse_flush()
        yield _sse_event(
            "done",
            _finish_payload(response=instant_query, model=_stream_model_label()),
        )
        return

    yield _sse_event("status", {"text": "Preparando respuesta…"})
    yield _sse_flush()

    if (
        is_finance_write_intent(text)
        or is_finance_pending_write(text)
        or is_finance_pending_query(text)
    ):
        payload = _register_movement(user_id, text)
        yield _sse_event("token", {"text": payload["response"]})
        yield _sse_event("done", payload)
        return

    try:
        anthropic_key, google_key = _ensure_llm_providers(needs_anthropic=False)
    except ValueError:
        fallback = _instant_finance_query_reply(user_id, text) or (
            "Disculpe señor, finanzas no está disponible en este momento."
        )
        yield from _yield_done_with_text(
            _finish_payload(response=fallback, model=_stream_model_label())
        )
        return

    if _needs_finance_tools(text, history_rows):
        yield _sse_event("status", {"text": "Analizando sus finanzas…"})
        yield _sse_flush()
        try:
            result = send_finance_message(
                user_id, message=text, history=history, conversation_id=conv_id
            )
        except Exception:  # noqa: BLE001
            logger.exception("[FINANCE] tools pipeline failed")
            result = _finish_payload(
                response="Disculpe señor, tuve un inconveniente. ¿Puede repetir?",
                model=_stream_model_label(),
            )
        yield from _yield_done_with_text(result)
        return

    system = _finance_system_with_data(FINANCE_STREAM_SYSTEM, user_id)
    stream_messages = [*_history_for_stream(history), {"role": "user", "content": text}]
    max_tokens = _stream_max_tokens(text)

    accumulated: list[str] = []
    stream_buf = ""
    stream_label = _stream_model_label()
    try:
        from app.services.llama_service import use_llama
        from app.services.stream_delta import stream_piece_delta

        if google_key or use_llama():
            for piece in _gemini_simple_reply_stream(
                api_key=google_key,
                model=_gemini_chat_model(),
                system=system,
                messages=stream_messages,
                max_tokens=max_tokens,
            ):
                delta = stream_piece_delta(stream_buf, piece)
                if not delta:
                    continue
                stream_buf += delta
                accumulated.append(delta)
                yield _sse_event("token", {"text": delta})
        elif anthropic_key:
            for piece, model_label in _iter_anthropic_text_stream(
                api_key=anthropic_key,
                system=system,
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
        logger.warning("[FINANCE] stream failed, fallback full: %s", exc)
        result = send_finance_message(
            user_id, message=text, history=history, conversation_id=conv_id
        )
        yield from _yield_done_with_text(result)
        return

    reply = _finalize_chat_reply("".join(accumulated).strip())
    if not reply:
        from app.services.cloud_llm_fallback import chat_cloud_reply

        cloud = chat_cloud_reply(
            system=system,
            messages=stream_messages,
            user_text=text,
            max_tokens=max_tokens,
        )
        if cloud:
            reply = _finalize_chat_reply(cloud)
    if not reply:
        instant = _instant_finance_query_reply(user_id, text)
        if instant:
            reply = instant
    if not reply:
        result = send_finance_message(
            user_id, message=text, history=history, conversation_id=conv_id
        )
        yield from _yield_done_with_text(result)
        return

    yield _sse_event("done", _finish_payload(response=reply, model=stream_label))


def finance_is_configured() -> bool:
    from app.services.claude_advanced import advanced_is_configured
    from app.services.cloud_llm_fallback import cloud_llm_configured
    from app.services.llama_service import should_route_to_llama, use_llama

    return (
        advanced_is_configured()
        or cloud_llm_configured()
        or (use_llama() and should_route_to_llama())
    )
