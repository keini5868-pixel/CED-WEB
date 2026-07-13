"""Piloto Retell LLM nativo — prompt, gateway get_environment y métricas."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from app.services.voice_test_mode import GEMINI_STANDALONE_SYSTEM

logger = logging.getLogger(__name__)

STAGING_AGENT_NAME = "CED Jarvis Native Pilot"

NATIVE_PILOT_GREETING = "CED en línea, señor. Estoy listo para conversar."

RETELL_NATIVE_PILOT_PROMPT = f"""{GEMINI_STANDALONE_SYSTEM}

Herramienta disponible (solo cuando el usuario la pida explícitamente):
- get_environment: clima, temperatura, pronóstico, calidad del aire, polen o ambiente en una ubicación.

Reglas de la herramienta:
- Úsala SOLO ante peticiones activas de información ambiental (ej. "¿cómo está el clima?", "dame información del clima",
  "calidad de aire", "¿va a llover?").
- NO la uses para charla casual, agradecimientos ("ok gracias"), check-ins ("¿me escuchas?", "¿estás ahí?"),
  desahogo personal ni menciones pasajeras del clima sin petición de datos.
- Si falta ubicación, pregunta una sola vez cuál ciudad o zona le interesa; luego llama get_environment con la query completa.
- Tras recibir el resultado, responde en 1-3 oraciones con los datos. No repitas la consulta ni vuelvas a llamar
  la herramienta sin una petición nueva del usuario.
""".strip()

GET_ENVIRONMENT_DESCRIPTION = (
    "Consulta clima, temperatura, pronóstico, calidad del aire o polen para una ubicación. "
    "Usar solo cuando el usuario pida activamente información ambiental en tiempo real."
)

GET_ENVIRONMENT_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": (
                "Petición completa del usuario sobre clima, calidad del aire o ambiente, "
                "incluyendo ubicación si la mencionó (ej. 'clima hoy en Charlotte', "
                "'calidad del aire Carolina del Norte')."
            ),
        },
    },
    "required": ["query"],
}

_lock = threading.Lock()
_tool_metrics: list[dict[str, Any]] = []
_call_metrics: dict[str, dict[str, Any]] = {}


def build_get_environment_tool(*, api_public_url: str) -> dict[str, Any]:
    base = api_public_url.rstrip("/")
    return {
        "type": "custom",
        "name": "get_environment",
        "description": GET_ENVIRONMENT_DESCRIPTION,
        "url": f"{base}/v1/retell/tools/get_environment",
        "method": "POST",
        "parameters": GET_ENVIRONMENT_PARAMETERS,
        "speak_during_execution": True,
        "speak_after_execution": True,
        "execution_message_description": "Consultando el ambiente, señor",
        "timeout_ms": 22_000,
    }


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


def resolve_environment_tool_query(payload: dict[str, Any], args: dict[str, Any]) -> str:
    query = str(args.get("query") or args.get("transcript") or "").strip()
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
        if len(_tool_metrics) > 200:
            del _tool_metrics[: len(_tool_metrics) - 200]
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
    env_calls = [t for t in tools if t.get("tool") == "get_environment"]
    latencies = [int(t["latency_ms"]) for t in env_calls if t.get("latency_ms") is not None]
    avg_latency = round(sum(latencies) / len(latencies)) if latencies else None
    return {
        "tool_invocations": len(tools),
        "environment_invocations": len(env_calls),
        "environment_avg_latency_ms": avg_latency,
        "environment_latencies_ms": latencies[-20:],
        "recent_tools": tools[-20:],
        "calls_tracked": len(calls),
    }


def get_call_pilot_metrics(call_id: str) -> dict[str, Any] | None:
    with _lock:
        data = _call_metrics.get(call_id.strip())
        return dict(data) if data else None


async def execute_get_environment_tool(
    *,
    user_id: str,
    payload: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    import asyncio

    from app.modules.environment_module import handle_environment_query_sync

    started = time.perf_counter()
    call_id = _extract_call_id(payload)
    query = resolve_environment_tool_query(payload, args)

    if not user_id:
        latency_ms = int((time.perf_counter() - started) * 1000)
        record_tool_metric(
            call_id=call_id,
            tool_name="get_environment",
            latency_ms=latency_ms,
            ok=False,
            query=query,
        )
        return {
            "result": "No identifiqué al usuario, señor.",
            "latency_ms": latency_ms,
            "ok": False,
        }

    if not query:
        latency_ms = int((time.perf_counter() - started) * 1000)
        record_tool_metric(
            call_id=call_id,
            tool_name="get_environment",
            latency_ms=latency_ms,
            ok=False,
        )
        return {
            "result": "Señor, ¿de qué ciudad o zona desea el clima o la calidad del aire?",
            "latency_ms": latency_ms,
            "ok": False,
        }

    try:
        result = await asyncio.to_thread(handle_environment_query_sync, user_id, query)
        spoken = str(result.get("spoken") or "Completado, señor.").strip()
        ok = not spoken.startswith("No pude obtener")
    except Exception:  # noqa: BLE001
        logger.exception("[NATIVE-PILOT] get_environment failed user=%s", user_id[:8])
        spoken = (
            "No pude obtener datos ambientales en este momento, señor. "
            "Intente de nuevo en unos minutos."
        )
        ok = False

    latency_ms = int((time.perf_counter() - started) * 1000)
    record_tool_metric(
        call_id=call_id,
        tool_name="get_environment",
        latency_ms=latency_ms,
        ok=ok,
        query=query,
    )
    logger.info(
        "[NATIVE-PILOT] get_environment call=%s user=%s latency=%sms ok=%s",
        call_id[:12] if call_id else "?",
        user_id[:8],
        latency_ms,
        ok,
    )
    return {"result": spoken, "latency_ms": latency_ms, "ok": ok}
