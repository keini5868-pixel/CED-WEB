"""Piloto Retell LLM nativo — prompt, tools HTTP firmadas y métricas."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

import httpx

from app.services.voice_test_mode import GEMINI_STANDALONE_SYSTEM

logger = logging.getLogger(__name__)

STAGING_AGENT_NAME = "CED Jarvis Native Pilot"
NATIVE_PILOT_GREETING = "CED en línea, señor. Estoy listo para conversar."

READ_TOOLS_PROMPT = """
Herramientas (usar solo cuando el usuario lo pida explícitamente):
- get_environment: clima, temperatura, pronóstico, calidad del aire, polen o ambiente.
- list_calendar_events: consultar eventos, citas o recordatorios en Google Calendar (solo lectura).
- read_gmail: leer bandeja, categorías o correos de un remitente.
- gmail_prepare_send: preparar envío de correo (NUNCA envía — solo crea borrador y pide confirmación).
- gmail_confirm_send: ejecutar envío real SOLO tras confirmación explícita del usuario en voz.
- gmail_cancel_send: descartar borrador pendiente sin enviar.

Reglas generales:
- NO uses herramientas para charla casual, agradecimientos ("ok gracias"), check-ins ("¿me escuchas?"),
  desahogo personal ni menciones pasajeras sin petición de datos.
- Tras recibir el resultado, responde en 1-4 oraciones. No repitas la consulta ni vuelvas a llamar
  la herramienta sin una petición nueva del usuario.
- NO agendes citas ni modifiques calendario — solo lectura de calendario en este piloto.

Gmail — envío con confirmación obligatoria:
1. gmail_prepare_send requiere destinatario, asunto Y cuerpo. El asunto es OBLIGATORIO — si falta,
   pregunta «¿Cuál es el asunto del correo?» y NO infieras asunto del cuerpo.
2. Tras prepare exitoso (awaiting_confirmation), lee el resumen en voz y pregunta si confirma el envío.
3. Llama transition_to_gmail_confirm_pending cuando prepare devuelva awaiting_confirmation.
4. gmail_confirm_send SOLO cuando el usuario acaba de decir sí/envíalo/dale de forma explícita.
5. NUNCA llames gmail_confirm_send en el mismo turno que gmail_prepare_send.
6. Si el usuario dice no/cancela → gmail_cancel_send y transition_to_general_assistant.
7. Si corrige destinatario/asunto/cuerpo antes de confirmar → cancela, vuelve a general_assistant
   y llama gmail_prepare_send con los datos corregidos.

get_environment / list_calendar_events / read_gmail: reglas de lectura igual que antes.
""".strip()

GENERAL_ASSISTANT_STATE_PROMPT = """
Estado general — clima, calendario (lectura), Gmail (lectura y preparar envío).
- Para ENVIAR correo: gmail_prepare_send con to, subject (obligatorio) y body.
- Si falta asunto, destinatario o cuerpo, pregunta antes de llamar la herramienta o deja que la tool lo indique.
- Tras prepare con awaiting_confirmation: lee el resumen, pregunta confirmación y usa transition_to_gmail_confirm_pending.
""".strip()

GMAIL_CONFIRM_STATE_PROMPT = """
Estado de confirmación de envío Gmail — hay un borrador pendiente.
- Repite el resumen si el usuario lo pide.
- Si confirma explícitamente (sí, envíalo, dale, adelante) → gmail_confirm_send.
- Si dice no, cancela, olvídalo o cambia de tema → gmail_cancel_send y transition_to_general_assistant.
- Si corrige datos → gmail_cancel_send, transition_to_general_assistant, gmail_prepare_send con datos nuevos.
- NO uses get_environment ni list_calendar_events aquí. read_gmail solo si pide leer correos (cancela el envío).
- NUNCA llames gmail_confirm_send sin confirmación verbal clara del usuario en este turno.
""".strip()

STATE_GENERAL_ASSISTANT = "general_assistant"
STATE_GMAIL_CONFIRM_PENDING = "gmail_confirm_pending"

RETELL_NATIVE_PILOT_PROMPT = f"{GEMINI_STANDALONE_SYSTEM}\n\n{READ_TOOLS_PROMPT}"

GET_ENVIRONMENT_DESCRIPTION = (
    "Consulta clima, temperatura, pronóstico, calidad del aire o polen para una ubicación. "
    "Usar solo cuando el usuario pida activamente información ambiental en tiempo real."
)

LIST_CALENDAR_DESCRIPTION = (
    "Consulta eventos, citas o recordatorios del Google Calendar del usuario. "
    "Solo lectura — no crear ni modificar eventos."
)

READ_GMAIL_DESCRIPTION = (
    "Lee correos de Gmail: bandeja, categoría o remitente. "
    "No envía correos — para enviar use gmail_prepare_send."
)

GMAIL_PREPARE_DESCRIPTION = (
    "Prepara un borrador de correo Gmail para envío. Requiere destinatario (to), "
    "asunto (subject, obligatorio) y cuerpo (body). NO envía — solo crea borrador "
    "y devuelve resumen para confirmación del usuario."
)

GMAIL_CONFIRM_DESCRIPTION = (
    "Ejecuta el envío real del borrador Gmail pendiente. "
    "SOLO llamar cuando el usuario acaba de confirmar explícitamente en voz "
    "(sí, envíalo, dale, adelante). Requiere draft_id del prepare."
)

GMAIL_CANCEL_DESCRIPTION = (
    "Cancela y descarta el borrador de correo pendiente sin enviar. "
    "Usar cuando el usuario dice no, cancela, olvídalo o desea corregir y rehacer."
)

GET_ENVIRONMENT_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": (
                "Petición completa sobre clima o ambiente, con ubicación si la mencionó."
            ),
        },
    },
    "required": ["query"],
}

LIST_CALENDAR_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": (
                "Petición del usuario sobre su calendario "
                "(ej. 'qué tengo hoy', 'eventos de mañana', 'esta semana')."
            ),
        },
    },
    "required": ["query"],
}

READ_GMAIL_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": (
                "Petición de lectura de correo tal cual "
                "(ej. 'léeme mis correos', 'correos importantes', 'email de Juan')."
            ),
        },
    },
    "required": ["query"],
}

GMAIL_PREPARE_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "to": {
            "type": "string",
            "description": "Correo del destinatario (ej. jessica.25@gmail.com).",
        },
        "subject": {
            "type": "string",
            "description": "Asunto del correo — OBLIGATORIO. No inferir del cuerpo.",
        },
        "body": {
            "type": "string",
            "description": "Cuerpo/mensaje del correo.",
        },
        "query": {
            "type": "string",
            "description": "Petición original del usuario si ayuda a extraer campos.",
        },
    },
    "required": ["body"],
}

GMAIL_CONFIRM_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "draft_id": {
            "type": "string",
            "description": "ID del borrador devuelto por gmail_prepare_send.",
        },
    },
    "required": ["draft_id"],
}

GMAIL_CANCEL_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "draft_id": {
            "type": "string",
            "description": "ID del borrador a cancelar (opcional si hay uno activo).",
        },
    },
}

_lock = threading.Lock()
_tool_metrics: list[dict[str, Any]] = []
_call_metrics: dict[str, dict[str, Any]] = {}


def _build_custom_tool(
    *,
    api_public_url: str,
    name: str,
    description: str,
    parameters: dict[str, Any],
    filler: str,
    timeout_ms: int,
) -> dict[str, Any]:
    base = api_public_url.rstrip("/")
    return {
        "type": "custom",
        "name": name,
        "description": description,
        "url": f"{base}/v1/retell/tools/{name}",
        "method": "POST",
        "parameters": parameters,
        "speak_during_execution": True,
        "speak_after_execution": True,
        "execution_message_type": "static_text",
        "execution_message_description": filler,
        "timeout_ms": timeout_ms,
    }


def build_get_environment_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="get_environment",
        description=GET_ENVIRONMENT_DESCRIPTION,
        parameters=GET_ENVIRONMENT_PARAMETERS,
        filler="Un momento, consultando el clima, señor.",
        timeout_ms=22_000,
    )


def build_list_calendar_events_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="list_calendar_events",
        description=LIST_CALENDAR_DESCRIPTION,
        parameters=LIST_CALENDAR_PARAMETERS,
        filler="Un momento, revisando su calendario, señor.",
        timeout_ms=18_000,
    )


def build_read_gmail_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="read_gmail",
        description=READ_GMAIL_DESCRIPTION,
        parameters=READ_GMAIL_PARAMETERS,
        filler="Un momento, revisando su correo, señor.",
        timeout_ms=24_000,
    )


def build_gmail_prepare_send_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="gmail_prepare_send",
        description=GMAIL_PREPARE_DESCRIPTION,
        parameters=GMAIL_PREPARE_PARAMETERS,
        filler="Un momento, preparando su correo, señor.",
        timeout_ms=12_000,
    )


def build_gmail_confirm_send_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="gmail_confirm_send",
        description=GMAIL_CONFIRM_DESCRIPTION,
        parameters=GMAIL_CONFIRM_PARAMETERS,
        filler="Enviando su correo, señor.",
        timeout_ms=20_000,
    )


def build_gmail_cancel_send_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="gmail_cancel_send",
        description=GMAIL_CANCEL_DESCRIPTION,
        parameters=GMAIL_CANCEL_PARAMETERS,
        filler="Un momento, señor.",
        timeout_ms=8_000,
    )


def build_native_pilot_states(*, api_public_url: str) -> tuple[list[dict[str, Any]], str]:
    """Retell States — tools restringidas por estado (general_tools vacío)."""
    return [
        {
            "name": STATE_GENERAL_ASSISTANT,
            "state_prompt": GENERAL_ASSISTANT_STATE_PROMPT,
            "tools": [
                build_get_environment_tool(api_public_url=api_public_url),
                build_list_calendar_events_tool(api_public_url=api_public_url),
                build_read_gmail_tool(api_public_url=api_public_url),
                build_gmail_prepare_send_tool(api_public_url=api_public_url),
            ],
            "edges": [
                {
                    "destination_state_name": STATE_GMAIL_CONFIRM_PENDING,
                    "description": (
                        "Transición cuando gmail_prepare_send devuelve awaiting_confirmation: "
                        "hay borrador listo y debe pedirse confirmación de envío al usuario."
                    ),
                },
            ],
        },
        {
            "name": STATE_GMAIL_CONFIRM_PENDING,
            "state_prompt": GMAIL_CONFIRM_STATE_PROMPT,
            "tools": [
                build_read_gmail_tool(api_public_url=api_public_url),
                build_gmail_confirm_send_tool(api_public_url=api_public_url),
                build_gmail_cancel_send_tool(api_public_url=api_public_url),
            ],
            "edges": [
                {
                    "destination_state_name": STATE_GENERAL_ASSISTANT,
                    "description": (
                        "Volver al flujo general tras envío exitoso, cancelación, borrador expirado "
                        "o cuando ya no hay correo pendiente."
                    ),
                },
            ],
        },
    ], STATE_GENERAL_ASSISTANT


def build_native_pilot_llm_config(*, api_public_url: str) -> dict[str, Any]:
    """Config LLM completa: states + starting_state, sin general_tools globales."""
    states, starting = build_native_pilot_states(api_public_url=api_public_url)
    return {
        "general_tools": [],
        "states": states,
        "starting_state": starting,
    }


def build_native_pilot_tools(*, api_public_url: str) -> list[dict[str, Any]]:
    """Lista plana de tools (tests / compat) — incluye todas las del piloto."""
    states, _ = build_native_pilot_states(api_public_url=api_public_url)
    tools: list[dict[str, Any]] = []
    for state in states:
        tools.extend(state.get("tools") or [])
    return tools


def _extract_call_id(payload: dict[str, Any]) -> str:
    call = payload.get("call") or {}
    return str(call.get("call_id") or call.get("callId") or "").strip()


def _latest_user_utterance(payload: dict[str, Any]) -> str:
    call = payload.get("call") or {}
    transcript_obj = call.get("transcript_object") or call.get("transcriptObject") or []
    if isinstance(transcript_obj, list):
        for entry in reversed(transcript_obj):
            if not isinstance(entry, dict):
                continue
            role = str(entry.get("role") or "").lower()
            if role in {"user", "customer"}:
                content = str(entry.get("content") or entry.get("text") or "").strip()
                if content:
                    return content
    transcript = str(call.get("transcript") or "").strip()
    if transcript:
        lines = [ln.strip() for ln in transcript.splitlines() if ln.strip()]
        for line in reversed(lines):
            lower = line.lower()
            if lower.startswith("user:") or lower.startswith("agent:"):
                prefix = "user:" if lower.startswith("user:") else "agent:"
                text = line.split(":", 1)[-1].strip()
                if prefix == "user:" and text:
                    return text
            elif not lower.startswith("agent:"):
                return line
    return ""


def resolve_tool_query(payload: dict[str, Any], args: dict[str, Any]) -> str:
    query = str(
        args.get("query")
        or args.get("consulta")
        or args.get("transcript")
        or ""
    ).strip()
    if query:
        return query
    from_transcript = _latest_user_utterance(payload)
    if from_transcript:
        return from_transcript
    return ""


def record_tool_metric(
    *,
    call_id: str,
    tool_name: str,
    latency_ms: int,
    ok: bool,
    query: str = "",
) -> None:
    entry = {
        "call_id": call_id or "unknown",
        "tool": tool_name,
        "latency_ms": latency_ms,
        "ok": ok,
        "query_preview": (query or "")[:120],
        "ts": time.time(),
    }
    with _lock:
        _tool_metrics.append(entry)
        if len(_tool_metrics) > 400:
            del _tool_metrics[: len(_tool_metrics) - 400]
        if call_id:
            bucket = _call_metrics.setdefault(
                call_id,
                {"call_id": call_id, "tools": [], "started_at": time.time()},
            )
            bucket["tools"].append(entry)


def get_pilot_metrics_snapshot() -> dict[str, Any]:
    with _lock:
        tools = list(_tool_metrics)
        calls = {cid: dict(data) for cid, data in _call_metrics.items()}

    def _stats(name: str) -> dict[str, Any]:
        rows = [t for t in tools if t.get("tool") == name]
        latencies = [int(t["latency_ms"]) for t in rows if t.get("latency_ms") is not None]
        avg = round(sum(latencies) / len(latencies)) if latencies else None
        return {
            "invocations": len(rows),
            "avg_latency_ms": avg,
            "latencies_ms": latencies[-20:],
        }

    return {
        "tool_invocations": len(tools),
        "calls_tracked": len(calls),
        "get_environment": _stats("get_environment"),
        "list_calendar_events": _stats("list_calendar_events"),
        "read_gmail": _stats("read_gmail"),
        "gmail_prepare_send": _stats("gmail_prepare_send"),
        "gmail_confirm_send": _stats("gmail_confirm_send"),
        "gmail_cancel_send": _stats("gmail_cancel_send"),
        "environment_invocations": _stats("get_environment")["invocations"],
        "environment_avg_latency_ms": _stats("get_environment")["avg_latency_ms"],
        "environment_latencies_ms": _stats("get_environment")["latencies_ms"],
        "recent_tools": tools[-30:],
    }


def get_call_pilot_metrics(call_id: str) -> dict[str, Any] | None:
    with _lock:
        data = _call_metrics.get(call_id.strip())
        return dict(data) if data else None


_FAILURE_SPOKEN_MARKERS = (
    "no pude",
    "no identifiqu",
    "aún no tiene",
    "reconect",
    "no está disponible",
    "permisos",
)


def _spoken_indicates_failure(spoken: str) -> bool:
    low = (spoken or "").lower()
    return any(marker in low for marker in _FAILURE_SPOKEN_MARKERS)


async def _execute_native_read_tool(
    *,
    tool_name: str,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any],
    handler: Callable[[str, str], dict[str, str]],
    empty_query_message: str,
    failure_prefix: str = "No pude completar",
) -> dict[str, Any]:
    import asyncio

    started = time.perf_counter()
    call_id = _extract_call_id(payload)
    query = resolve_tool_query(payload, args)

    if not user_id:
        latency_ms = int((time.perf_counter() - started) * 1000)
        record_tool_metric(
            call_id=call_id,
            tool_name=tool_name,
            latency_ms=latency_ms,
            ok=False,
            query=query,
        )
        return {
            "result": "No identifiqué al usuario, señor.",
            "latency_ms": latency_ms,
            "ok": False,
        }

    from app.services.gmail_send_flow import maybe_clear_gmail_pending_on_topic_change

    maybe_clear_gmail_pending_on_topic_change(user_id, tool_name)

    if not query:
        latency_ms = int((time.perf_counter() - started) * 1000)
        record_tool_metric(
            call_id=call_id,
            tool_name=tool_name,
            latency_ms=latency_ms,
            ok=False,
        )
        return {
            "result": empty_query_message,
            "latency_ms": latency_ms,
            "ok": False,
        }

    try:
        result = await asyncio.to_thread(handler, user_id, query)
        spoken = str(result.get("spoken") or "Completado, señor.").strip()
        ok = not _spoken_indicates_failure(spoken)
    except httpx.HTTPStatusError as exc:
        logger.error(
            "[NATIVE-PILOT] %s HTTP %s user=%s",
            tool_name,
            exc.response.status_code,
            user_id[:8],
        )
        spoken = f"{failure_prefix} en este momento, señor. Revise la conexión de Google."
        ok = False
    except ValueError as exc:
        if str(exc) == "not_connected":
            spoken = (
                "Señor, aún no tiene esa integración conectada. "
                "Use el botón correspondiente en configuración de voz."
            )
        else:
            spoken = f"{failure_prefix} en este momento, señor."
        ok = False
    except Exception:  # noqa: BLE001
        logger.exception("[NATIVE-PILOT] %s failed user=%s", tool_name, user_id[:8])
        spoken = f"{failure_prefix} en este momento, señor. Intente de nuevo en unos minutos."
        ok = False

    latency_ms = int((time.perf_counter() - started) * 1000)
    record_tool_metric(
        call_id=call_id,
        tool_name=tool_name,
        latency_ms=latency_ms,
        ok=ok,
        query=query,
    )
    logger.info(
        "[NATIVE-PILOT] %s call=%s user=%s latency=%sms ok=%s",
        tool_name,
        call_id[:12] if call_id else "?",
        user_id[:8],
        latency_ms,
        ok,
    )
    return {"result": spoken, "latency_ms": latency_ms, "ok": ok}


async def execute_get_environment_tool(
    *,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    from app.modules.environment_module import handle_environment_query_sync

    return await _execute_native_read_tool(
        tool_name="get_environment",
        user_id=user_id,
        payload=payload,
        args=args,
        handler=handle_environment_query_sync,
        empty_query_message="Señor, ¿de qué ciudad o zona desea el clima o la calidad del aire?",
        failure_prefix="No pude obtener datos ambientales",
    )


async def execute_list_calendar_events_tool(
    *,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    from app.modules.calendar_module import handle_calendar_read_sync

    return await _execute_native_read_tool(
        tool_name="list_calendar_events",
        user_id=user_id,
        payload=payload,
        args=args,
        handler=handle_calendar_read_sync,
        empty_query_message="Señor, ¿qué día o periodo de su calendario desea consultar?",
        failure_prefix="No pude consultar su calendario",
    )


async def execute_read_gmail_tool(
    *,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    from app.modules.gmail_module import handle_gmail_read_sync
    from app.services.gmail_send_flow import maybe_clear_gmail_pending_on_topic_change

    maybe_clear_gmail_pending_on_topic_change(user_id, "read_gmail")

    return await _execute_native_read_tool(
        tool_name="read_gmail",
        user_id=user_id,
        payload=payload,
        args=args,
        handler=handle_gmail_read_sync,
        empty_query_message="Señor, ¿qué correos desea que revise?",
        failure_prefix="No pude consultar su correo",
    )


def _format_gmail_action_result(action: dict[str, Any]) -> str:
    """Resultado hablado + metadata JSON para el LLM (transiciones Retell)."""
    import json

    spoken = str(action.get("spoken") or "Completado, señor.").strip()
    meta = {
        "status": action.get("status"),
        "draft_id": action.get("draft_id"),
        "transition": action.get("transition"),
        "ok": action.get("ok"),
    }
    meta = {k: v for k, v in meta.items() if v is not None}
    if meta:
        return f"{spoken}\n\n[meta:{json.dumps(meta, ensure_ascii=False)}]"
    return spoken


async def _execute_native_gmail_action_tool(
    *,
    tool_name: str,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any],
    handler: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    import asyncio

    started = time.perf_counter()
    call_id = _extract_call_id(payload)

    if not user_id:
        latency_ms = int((time.perf_counter() - started) * 1000)
        record_tool_metric(
            call_id=call_id,
            tool_name=tool_name,
            latency_ms=latency_ms,
            ok=False,
        )
        return {
            "result": "No identifiqué al usuario, señor.",
            "latency_ms": latency_ms,
            "ok": False,
        }

    try:
        action = await asyncio.to_thread(
            handler,
            user_id,
            call_id=call_id,
            payload=payload,
            args=args,
        )
        spoken = _format_gmail_action_result(action)
        ok = bool(action.get("ok"))
    except Exception:  # noqa: BLE001
        logger.exception("[NATIVE-PILOT] %s failed user=%s", tool_name, user_id[:8])
        spoken = "Señor, no pude completar la operación de correo en este momento."
        ok = False

    latency_ms = int((time.perf_counter() - started) * 1000)
    record_tool_metric(
        call_id=call_id,
        tool_name=tool_name,
        latency_ms=latency_ms,
        ok=ok,
        query=str(args.get("draft_id") or args.get("to") or "")[:120],
    )
    return {"result": spoken, "latency_ms": latency_ms, "ok": ok}


def _run_gmail_prepare(user_id: str, *, call_id: str, payload: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    from app.services.gmail_send_flow import prepare_gmail_send

    query = resolve_tool_query(payload, args)
    return prepare_gmail_send(
        user_id,
        call_id=call_id,
        to=str(args.get("to") or ""),
        subject=str(args.get("subject") or ""),
        body=str(args.get("body") or ""),
        query=query,
    )


def _run_gmail_confirm(user_id: str, *, call_id: str, payload: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    from app.services.gmail_send_flow import confirm_gmail_send

    return confirm_gmail_send(
        user_id,
        call_id=call_id,
        payload=payload,
        draft_id=str(args.get("draft_id") or ""),
    )


def _run_gmail_cancel(user_id: str, *, call_id: str, payload: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    from app.services.gmail_send_flow import cancel_gmail_send

    return cancel_gmail_send(
        user_id,
        draft_id=str(args.get("draft_id") or ""),
        reason="user_cancel",
    )


async def execute_gmail_prepare_send_tool(
    *,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    return await _execute_native_gmail_action_tool(
        tool_name="gmail_prepare_send",
        user_id=user_id,
        payload=payload,
        args=args,
        handler=_run_gmail_prepare,
    )


async def execute_gmail_confirm_send_tool(
    *,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    return await _execute_native_gmail_action_tool(
        tool_name="gmail_confirm_send",
        user_id=user_id,
        payload=payload,
        args=args,
        handler=_run_gmail_confirm,
    )


async def execute_gmail_cancel_send_tool(
    *,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    return await _execute_native_gmail_action_tool(
        tool_name="gmail_cancel_send",
        user_id=user_id,
        payload=payload,
        args=args,
        handler=_run_gmail_cancel,
    )


# Compat tests / imports previos
resolve_environment_tool_query = resolve_tool_query
