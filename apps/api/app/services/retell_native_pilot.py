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
- read_gmail: leer bandeja, categorías o correos de un remitente (SOLO lectura — incluye cuerpo completo).
- read_finances: resumen financiero, desglose de gastos o pagos pendientes (solo lectura).
- finance_prepare_write: preparar registro de gasto, ingreso o pago pendiente (NUNCA guarda — solo borrador).
- finance_confirm_write: ejecutar registro real SOLO tras confirmación explícita del usuario en voz.
- finance_cancel_write: descartar borrador financiero pendiente sin guardar.
- activate_camera: encender la cámara del dispositivo (una sola vez).
- deactivate_camera: apagar la cámara.
- analyze_camera_frame: describir qué hay frente a la cámara (visión).
- search_visible_product: identificar el objeto visible y buscar datos reales (precio, specs, dónde comprarlo).

Reglas generales:
- NO uses herramientas para charla casual, agradecimientos ("ok gracias"), check-ins ("¿me escuchas?"),
  desahogo personal ni menciones pasajeras sin petición de datos.
- Tras recibir el resultado, responde en 1-4 oraciones. No repitas la consulta ni vuelvas a llamar
  la herramienta sin una petición nueva del usuario.
- EXCEPCIÓN Gmail: tras read_gmail, lee al usuario el texto devuelto por la herramienta tal cual, sin modificarlo ni añadir nada.
- EXCEPCIÓN Finanzas confirmación: tras finance_confirm_write exitoso, di el mensaje de confirmación sin parafrasear.
- EXCEPCIÓN Cámara: tras activate/deactivate/analyze/search, di el resultado de la herramienta tal cual.
- NO agendes citas ni modifiques calendario — solo lectura de calendario en este piloto.
- NO envíes correos por voz — Gmail es solo lectura. Para enviar, el usuario usa el formulario en pantalla.

Gmail — solo lectura:
- read_gmail devuelve el texto exacto que debe decirse en voz; repítalo sin inventar ni resumir.
- PROHIBIDO prometer «voy a extraer el cuerpo» — si la tool dice que no pudo, comuníquelo una vez y pare.
- Si el usuario pide enviar correo, indíquele que use el formulario de correo en la interfaz de CED.

Cámara / visión:
1. «activa/enciende/abre la cámara» → activate_camera UNA sola vez. NO vuelvas a confirmar la activación.
2. PROHIBIDO describir nada visual sin llamar analyze_camera_frame o search_visible_product.
3. «qué ves / qué es esto / analiza» → analyze_camera_frame (si la cámara está apagada, la tool la activa internamente).
4. «dónde lo compro / precio / especificaciones / marca» → search_visible_product.
5. «apaga/cierra la cámara» → deactivate_camera.
6. Si falla captura o permisos, comunica el error UNA vez — sin bucles de «activando, activando».

Finanzas — escritura con confirmación obligatoria:
1. finance_prepare_write requiere monto y concepto claros (gasto, ingreso o pago pendiente con fecha).
2. Tras prepare exitoso (awaiting_confirmation), lee el resumen en voz y pregunta si confirma el registro.
3. Llama transition_to_finance_confirm_pending cuando prepare devuelva awaiting_confirmation.
4. finance_confirm_write cuando el usuario dice sí, sí., dale, adelante o confirma — incluso solo «sí».
5. NUNCA llames finance_confirm_write en el mismo turno que finance_prepare_write.
6. Si el usuario dice no/cancela → finance_cancel_write y transition_to_general_assistant.
7. Si hay borrador pendiente y el usuario dice «sí», llama finance_confirm_write aunque no hayas cambiado de estado.

read_finances / get_environment / list_calendar_events / read_gmail: reglas de lectura sin confirmación.
""".strip()

GENERAL_ASSISTANT_STATE_PROMPT = """
Estado general — clima, calendario (lectura), Gmail (solo lectura), finanzas (lectura y preparar registro), cámara.
- Gmail: solo lectura. Repite el resultado de read_gmail tal cual.
- Cámara: activate_camera una sola vez; describe solo con analyze_camera_frame / search_visible_product.
- Para REGISTRAR finanzas: finance_prepare_write con la frase del usuario (monto + concepto).
- Tras prepare con awaiting_confirmation: lee el resumen, pregunta confirmación y usa transition_to_finance_confirm_pending.
- Si ya hay borrador pendiente y el usuario dice «sí» o «dale», llama finance_confirm_write de inmediato (también disponible aquí).
""".strip()

FINANCE_CONFIRM_STATE_PROMPT = """
Estado de confirmación de registro financiero — hay un borrador pendiente.
- Repite el resumen si el usuario lo pide.
- Si dice sí, sí., dale, adelante o confirma → finance_confirm_write de inmediato (incluso solo «sí»).
- Si dice no, cancela, olvídalo o cambia de tema → finance_cancel_write y transition_to_general_assistant.
- Si corrige datos → finance_cancel_write, transition_to_general_assistant, finance_prepare_write con datos nuevos.
- read_finances solo si pide consultar finanzas (cancela el registro pendiente).
- Tras finance_confirm_write exitoso, di al usuario exactamente el mensaje de confirmación devuelto.
""".strip()

STATE_GENERAL_ASSISTANT = "general_assistant"
STATE_FINANCE_CONFIRM_PENDING = "finance_confirm_pending"

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
    "Lee correos de Gmail: bandeja, categoría o remitente, incluyendo el cuerpo completo del mensaje. "
    "No envía correos — para enviar use el formulario en la interfaz de CED."
)

READ_FINANCES_DESCRIPTION = (
    "Consulta finanzas personales: resumen del mes, desglose de gastos o lista de pagos pendientes. "
    "Solo lectura — no registra movimientos."
)

FINANCE_PREPARE_DESCRIPTION = (
    "Prepara un borrador de registro financiero (gasto, ingreso o pago pendiente). "
    "Requiere monto y concepto en la frase del usuario. NO guarda — solo crea borrador "
    "y devuelve resumen para confirmación."
)

FINANCE_CONFIRM_DESCRIPTION = (
    "Ejecuta el registro real del borrador financiero pendiente. "
    "Llamar cuando el usuario acaba de confirmar en voz: sí, sí., dale, adelante, correcto. "
    "Un solo «sí» basta si hay borrador pendiente. draft_id opcional si hay uno activo."
)

FINANCE_CANCEL_DESCRIPTION = (
    "Cancela y descarta el borrador financiero pendiente sin guardar. "
    "Usar cuando el usuario dice no, cancela, olvídalo o desea corregir y rehacer."
)

ACTIVATE_CAMERA_DESCRIPTION = (
    "Enciende la cámara del dispositivo del usuario. "
    "Usar cuando diga activa/enciende/abre la cámara. "
    "Si ya está activa, responde sin reactivar. NO describe lo que ve — solo confirma activación."
)

DEACTIVATE_CAMERA_DESCRIPTION = (
    "Apaga la cámara del dispositivo. "
    "Usar cuando diga apaga/cierra/desactiva la cámara."
)

ANALYZE_CAMERA_FRAME_DESCRIPTION = (
    "Captura un frame de la cámara y describe qué hay frente a ella. "
    "Usar para 'qué ves', 'qué es esto', 'analiza lo que muestro'. "
    "Si la cámara está apagada, la activa internamente. "
    "PROHIBIDO inventar una descripción sin llamar esta herramienta."
)

SEARCH_VISIBLE_PRODUCT_DESCRIPTION = (
    "Identifica el objeto visible ante la cámara y busca información real "
    "(especificaciones, precio, dónde comprarlo, marca). "
    "Usar cuando el usuario pida datos adicionales sobre lo mostrado."
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
                "(ej. 'léeme mis correos', 'correos importantes', 'léeme el correo de Juan')."
            ),
        },
    },
    "required": ["query"],
}

READ_FINANCES_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": (
                "Petición de consulta financiera "
                "(ej. 'cómo voy este mes', 'desglose de gastos', 'pagos pendientes')."
            ),
        },
    },
    "required": ["query"],
}

FINANCE_PREPARE_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": (
                "Frase del usuario sobre el movimiento a registrar "
                "(ej. 'gasté 50 en materiales', 'el lunes tengo que pagar 850')."
            ),
        },
    },
    "required": ["query"],
}

FINANCE_CONFIRM_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "draft_id": {
            "type": "string",
            "description": "ID del borrador devuelto por finance_prepare_write (opcional si hay uno activo).",
        },
    },
}

FINANCE_CANCEL_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "draft_id": {
            "type": "string",
            "description": "ID del borrador a cancelar (opcional si hay uno activo).",
        },
    },
}

ACTIVATE_CAMERA_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {},
}

DEACTIVATE_CAMERA_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {},
}

ANALYZE_CAMERA_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "question": {
            "type": "string",
            "description": (
                "Pregunta opcional sobre lo visible "
                "(ej. 'qué marca es', 'qué producto muestro')."
            ),
        },
    },
}

SEARCH_VISIBLE_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "question": {
            "type": "string",
            "description": (
                "Pregunta del usuario sobre el producto visible "
                "(ej. 'dónde lo compro', 'especificaciones', 'precio')."
            ),
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


def build_read_finances_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="read_finances",
        description=READ_FINANCES_DESCRIPTION,
        parameters=READ_FINANCES_PARAMETERS,
        filler="Un momento, revisando sus finanzas, señor.",
        timeout_ms=18_000,
    )


def build_finance_prepare_write_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="finance_prepare_write",
        description=FINANCE_PREPARE_DESCRIPTION,
        parameters=FINANCE_PREPARE_PARAMETERS,
        filler="Un momento, preparando el registro, señor.",
        timeout_ms=12_000,
    )


def build_finance_confirm_write_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="finance_confirm_write",
        description=FINANCE_CONFIRM_DESCRIPTION,
        parameters=FINANCE_CONFIRM_PARAMETERS,
        filler="Registrando su movimiento, señor.",
        timeout_ms=20_000,
    )


def build_finance_cancel_write_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="finance_cancel_write",
        description=FINANCE_CANCEL_DESCRIPTION,
        parameters=FINANCE_CANCEL_PARAMETERS,
        filler="Un momento, señor.",
        timeout_ms=8_000,
    )


def build_activate_camera_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="activate_camera",
        description=ACTIVATE_CAMERA_DESCRIPTION,
        parameters=ACTIVATE_CAMERA_PARAMETERS,
        filler="Activando la cámara, señor.",
        timeout_ms=12_000,
    )


def build_deactivate_camera_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="deactivate_camera",
        description=DEACTIVATE_CAMERA_DESCRIPTION,
        parameters=DEACTIVATE_CAMERA_PARAMETERS,
        filler="Un momento, señor.",
        timeout_ms=8_000,
    )


def build_analyze_camera_frame_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="analyze_camera_frame",
        description=ANALYZE_CAMERA_FRAME_DESCRIPTION,
        parameters=ANALYZE_CAMERA_PARAMETERS,
        filler="Un momento, analizando lo que me muestra, señor.",
        timeout_ms=45_000,
    )


def build_search_visible_product_tool(*, api_public_url: str) -> dict[str, Any]:
    return _build_custom_tool(
        api_public_url=api_public_url,
        name="search_visible_product",
        description=SEARCH_VISIBLE_PRODUCT_DESCRIPTION,
        parameters=SEARCH_VISIBLE_PARAMETERS,
        filler="Un momento, buscando información sobre lo que veo, señor.",
        timeout_ms=45_000,
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
                build_read_finances_tool(api_public_url=api_public_url),
                build_finance_prepare_write_tool(api_public_url=api_public_url),
                build_finance_confirm_write_tool(api_public_url=api_public_url),
                build_finance_cancel_write_tool(api_public_url=api_public_url),
                build_activate_camera_tool(api_public_url=api_public_url),
                build_deactivate_camera_tool(api_public_url=api_public_url),
                build_analyze_camera_frame_tool(api_public_url=api_public_url),
                build_search_visible_product_tool(api_public_url=api_public_url),
            ],
            "edges": [
                {
                    "destination_state_name": STATE_FINANCE_CONFIRM_PENDING,
                    "description": (
                        "Transición cuando finance_prepare_write devuelve awaiting_confirmation: "
                        "hay borrador listo y debe pedirse confirmación de registro al usuario."
                    ),
                },
            ],
        },
        {
            "name": STATE_FINANCE_CONFIRM_PENDING,
            "state_prompt": FINANCE_CONFIRM_STATE_PROMPT,
            "tools": [
                build_read_finances_tool(api_public_url=api_public_url),
                build_finance_confirm_write_tool(api_public_url=api_public_url),
                build_finance_cancel_write_tool(api_public_url=api_public_url),
            ],
            "edges": [
                {
                    "destination_state_name": STATE_GENERAL_ASSISTANT,
                    "description": (
                        "Volver al flujo general tras registro exitoso, cancelación, borrador expirado "
                        "o cuando ya no hay movimiento pendiente."
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
        "read_finances": _stats("read_finances"),
        "finance_prepare_write": _stats("finance_prepare_write"),
        "finance_confirm_write": _stats("finance_confirm_write"),
        "finance_cancel_write": _stats("finance_cancel_write"),
        "activate_camera": _stats("activate_camera"),
        "deactivate_camera": _stats("deactivate_camera"),
        "analyze_camera_frame": _stats("analyze_camera_frame"),
        "search_visible_product": _stats("search_visible_product"),
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

    from app.services.finance_write_flow import maybe_clear_finance_pending_on_topic_change

    maybe_clear_finance_pending_on_topic_change(user_id, tool_name)

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

    return await _execute_native_read_tool(
        tool_name="read_gmail",
        user_id=user_id,
        payload=payload,
        args=args,
        handler=handle_gmail_read_sync,
        empty_query_message="Señor, ¿qué correos desea que revise?",
        failure_prefix="No pude consultar su correo",
    )


async def execute_read_finances_tool(
    *,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    from app.modules.finance_module import handle_finance_read_sync
    from app.services.finance_write_flow import maybe_clear_finance_pending_on_topic_change

    maybe_clear_finance_pending_on_topic_change(user_id, "read_finances")

    return await _execute_native_read_tool(
        tool_name="read_finances",
        user_id=user_id,
        payload=payload,
        args=args,
        handler=handle_finance_read_sync,
        empty_query_message="Señor, ¿qué desea consultar de sus finanzas?",
        failure_prefix="No pude consultar sus finanzas",
    )


def _format_finance_action_result(action: dict[str, Any]) -> str:
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


async def _execute_native_finance_action_tool(
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
        spoken = _format_finance_action_result(action)
        ok = bool(action.get("ok"))
    except Exception:  # noqa: BLE001
        logger.exception("[NATIVE-PILOT] %s failed user=%s", tool_name, user_id[:8])
        spoken = "Señor, no pude completar la operación de finanzas en este momento."
        ok = False

    latency_ms = int((time.perf_counter() - started) * 1000)
    record_tool_metric(
        call_id=call_id,
        tool_name=tool_name,
        latency_ms=latency_ms,
        ok=ok,
        query=str(args.get("draft_id") or args.get("query") or "")[:120],
    )
    return {"result": spoken, "latency_ms": latency_ms, "ok": ok}


def _run_finance_prepare(user_id: str, *, call_id: str, payload: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    from app.services.finance_write_flow import prepare_finance_write

    query = resolve_tool_query(payload, args)
    return prepare_finance_write(user_id, call_id=call_id, query=query)


def _run_finance_confirm(user_id: str, *, call_id: str, payload: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    from app.services.finance_write_flow import confirm_finance_write

    return confirm_finance_write(
        user_id,
        call_id=call_id,
        payload=payload,
        draft_id=str(args.get("draft_id") or ""),
    )


def _run_finance_cancel(user_id: str, *, call_id: str, payload: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    from app.services.finance_write_flow import cancel_finance_write

    return cancel_finance_write(
        user_id,
        draft_id=str(args.get("draft_id") or ""),
        reason="user_cancel",
    )


async def execute_finance_prepare_write_tool(
    *,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    return await _execute_native_finance_action_tool(
        tool_name="finance_prepare_write",
        user_id=user_id,
        payload=payload,
        args=args,
        handler=_run_finance_prepare,
    )


async def execute_finance_confirm_write_tool(
    *,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    return await _execute_native_finance_action_tool(
        tool_name="finance_confirm_write",
        user_id=user_id,
        payload=payload,
        args=args,
        handler=_run_finance_confirm,
    )


async def execute_finance_cancel_write_tool(
    *,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    return await _execute_native_finance_action_tool(
        tool_name="finance_cancel_write",
        user_id=user_id,
        payload=payload,
        args=args,
        handler=_run_finance_cancel,
    )


_PRODUCT_FOLLOWUP_RE = (
    r"\b("
    r"marca|brand|precio|cuesta|cuesta|comprar|consig|d[oó]nde\s+(?:lo\s+)?(?:compro|vendo|encuentro)|"
    r"especificaci|specs?|caracter[ií]stic|modelo|cu[aá]nto\s+(?:cuesta|vale)|"
    r"informaci[oó]n(?:\s+adicional)?|datos\s+(?:del\s+)?producto"
    r")\b"
)


def _camera_question_from_args(payload: dict[str, Any], args: dict[str, Any]) -> str:
    for key in ("question", "pregunta", "query"):
        value = str(args.get(key) or "").strip()
        if value:
            return value
    return resolve_tool_query(payload, args)


async def _execute_native_camera_tool(
    *,
    tool_name: str,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    """Wrappers sobre voice_tool_executor — misma lógica que Custom LLM / Live."""
    import re

    from app.services import voice_client_session as vcs
    from app.services.voice_tool_executor import execute_voice_tool

    started = time.perf_counter()
    call_id = _extract_call_id(payload)
    question = _camera_question_from_args(payload, args)

    if not user_id:
        latency_ms = int((time.perf_counter() - started) * 1000)
        record_tool_metric(
            call_id=call_id,
            tool_name=tool_name,
            latency_ms=latency_ms,
            ok=False,
            query=question,
        )
        return {
            "result": "No identifiqué al usuario, señor.",
            "latency_ms": latency_ms,
            "ok": False,
        }

    try:
        if tool_name == "activate_camera":
            # Idempotente: is_camera_active → respuesta corta sin re-push.
            result = await execute_voice_tool(
                "request_camera_activation",
                user_id,
                {},
            )
        elif tool_name == "deactivate_camera":
            result = await execute_voice_tool(
                "request_camera_deactivation",
                user_id,
                {},
            )
        elif tool_name == "analyze_camera_frame":
            result = await execute_voice_tool(
                "analyze_camera_frame",
                user_id,
                {"pregunta": question or "¿Qué ves en la imagen?"},
            )
        elif tool_name == "search_visible_product":
            last_vision = vcs.get_last_vision_summary(user_id)
            followup = bool(
                last_vision
                and question
                and re.search(_PRODUCT_FOLLOWUP_RE, question, re.I)
            )
            if followup:
                # Reutiliza el último objeto identificado + búsqueda web (sin recapturar).
                obj = re.sub(
                    r"(?i)^(es|se ve|parece)\s+(un|una)\s+",
                    "",
                    last_vision,
                ).strip()
                obj = re.sub(r"\s+", " ", obj)[:120]
                search_q = f"{obj} {question}".strip()[:200]
                result = await execute_voice_tool(
                    "search_web",
                    user_id,
                    {"query": search_q, "kind": "general"},
                )
                spoken_web = str(result.get("spoken") or "").strip()
                if spoken_web and result.get("ok", True):
                    result = {
                        "ok": True,
                        "spoken": (
                            f"Sobre lo que identificamos ({obj}): {spoken_web}"
                        ),
                    }
                else:
                    result = await execute_voice_tool(
                        "buscar_lo_visible",
                        user_id,
                        {
                            "pregunta": question
                            or "Identifica lo visible y busca información",
                        },
                    )
            else:
                result = await execute_voice_tool(
                    "buscar_lo_visible",
                    user_id,
                    {
                        "pregunta": question
                        or "Identifica lo visible y busca información",
                    },
                )
        else:
            result = {"ok": False, "spoken": "Herramienta de cámara no reconocida, señor."}

        spoken = str(result.get("spoken") or "Completado, señor.").strip()
        ok = bool(result.get("ok", True)) and not _spoken_indicates_failure(spoken)
    except Exception:  # noqa: BLE001
        logger.exception("[NATIVE-PILOT] %s failed user=%s", tool_name, user_id[:8])
        spoken = "Señor, no pude completar la operación de cámara en este momento."
        ok = False

    latency_ms = int((time.perf_counter() - started) * 1000)
    record_tool_metric(
        call_id=call_id,
        tool_name=tool_name,
        latency_ms=latency_ms,
        ok=ok,
        query=question[:120],
    )
    return {"result": spoken, "latency_ms": latency_ms, "ok": ok}


async def execute_activate_camera_tool(
    *,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    return await _execute_native_camera_tool(
        tool_name="activate_camera",
        user_id=user_id,
        payload=payload,
        args=args,
    )


async def execute_deactivate_camera_tool(
    *,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    return await _execute_native_camera_tool(
        tool_name="deactivate_camera",
        user_id=user_id,
        payload=payload,
        args=args,
    )


async def execute_analyze_camera_frame_tool(
    *,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    return await _execute_native_camera_tool(
        tool_name="analyze_camera_frame",
        user_id=user_id,
        payload=payload,
        args=args,
    )


async def execute_search_visible_product_tool(
    *,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    return await _execute_native_camera_tool(
        tool_name="search_visible_product",
        user_id=user_id,
        payload=payload,
        args=args,
    )


# Compat tests / imports previos
resolve_environment_tool_query = resolve_tool_query
