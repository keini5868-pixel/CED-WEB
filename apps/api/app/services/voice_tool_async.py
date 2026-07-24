"""Ejecución asíncrona de tools de voz — ack inmediato + resultado en background."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from google.genai import types

from app.services.retell_custom_llm import format_web_delivery
from app.services.voice_tool_executor import execute_voice_tool

logger = logging.getLogger(__name__)

TOOL_DEFAULT_TIMEOUT_SEC = 18.0
PDF_TOOL_TIMEOUT_SEC = 35.0
IMAGE_TOOL_TIMEOUT_SEC = 60.0
PUBLISH_TOOL_TIMEOUT_SEC = 35.0

_TOOL_ACK: dict[str, str] = {
    "search_web": "Investigando, señor.",
    "play_youtube_video": "Buscando en YouTube, señor.",
    "activar_modo_conducir": "Abriendo el mapa, señor.",
    "open_map": "Abriendo el mapa, señor.",
    "search_nearby_places": "Buscando en el mapa, señor.",
    "start_navigation": "Calculando ruta, señor.",
    "iniciar_navegacion": "Calculando ruta, señor.",
    "publicar_instagram": "Un momento, señor.",
    "publicar_facebook": "Un momento, señor.",
    "generar_pdf": "Preparando el PDF, señor.",
    "generate_image": "Un momento, generando su imagen, señor.",
    "analyze_camera_frame": "Analizando, señor.",
    "buscar_lo_visible": "Analizando, señor.",
    "registrar_movimiento_financiero": "Anotando el movimiento, señor.",
    "consultar_finanzas": "Revisando sus finanzas, señor.",
    "consultar_pagos_pendientes": "Revisando sus pagos pendientes, señor.",
}

_TOOL_FALLBACK: dict[str, str] = {
    "search_web": "Señor, no pude completar la búsqueda. ¿Repito?",
    "play_youtube_video": "No pude buscar el video en YouTube, señor. ¿Repito?",
    "generar_pdf": "No pude preparar el PDF, señor. ¿Lo intento de nuevo?",
    "generate_image": "No pude generar la imagen, señor. ¿Lo intento de nuevo?",
    "publicar_instagram": "No pude publicar en Instagram, señor.",
    "publicar_facebook": "No pude publicar en Facebook, señor.",
    "registrar_movimiento_financiero": "No pude anotar el movimiento, señor. ¿Lo repite?",
    "consultar_finanzas": "No pude revisar sus finanzas, señor. ¿Lo intento de nuevo?",
    "consultar_pagos_pendientes": "No pude revisar sus pagos pendientes, señor.",
}


def get_tool_acknowledgment(tool_name: str) -> str:
    key = (tool_name or "").strip().lower()
    return _TOOL_ACK.get(key, "Un momento, señor.")


def get_tool_fallback(tool_name: str) -> str:
    key = (tool_name or "").strip().lower()
    return _TOOL_FALLBACK.get(key, "Disculpe señor, hubo un inconveniente.")


def combined_tool_acknowledgment(tool_names: list[str]) -> str:
    if not tool_names:
        return "Un momento, señor."
    if len(tool_names) == 1:
        return get_tool_acknowledgment(tool_names[0])
    return get_tool_acknowledgment(tool_names[0])


def tool_timeout_sec(tool_name: str) -> float:
    key = (tool_name or "").strip().lower()
    if key == "generar_pdf":
        return PDF_TOOL_TIMEOUT_SEC
    if key == "generate_image":
        return IMAGE_TOOL_TIMEOUT_SEC
    if key in ("publicar_facebook", "publicar_instagram"):
        return PUBLISH_TOOL_TIMEOUT_SEC
    return TOOL_DEFAULT_TIMEOUT_SEC


@dataclass
class DeferredToolCall:
    name: str
    args: dict[str, Any]


@dataclass
class DeferredToolBatch:
    calls: list[DeferredToolCall] = field(default_factory=list)
    user_text: str = ""
    model_parts: list[types.Part] = field(default_factory=list)
    last_content: types.Content | None = None
    on_web_fallback: Callable[[], None] | None = None


DeliverFn = Callable[[str], Awaitable[bool]]


async def execute_deferred_tool_batch(
    batch: DeferredToolBatch,
    *,
    user_id: str | None,
    deliver: DeliverFn,
    is_stale: Callable[[], bool] | None = None,
    build_tool_payload: Callable[[str, dict[str, Any], dict[str, Any]], tuple[str, dict[str, Any]]]
    | None = None,
) -> list[tuple[str, dict[str, Any], str]]:
    """Ejecuta tools en background; entrega spoken final al usuario."""
    if is_stale and is_stale():
        return []

    results: list[tuple[str, dict[str, Any], str]] = []
    final_spoken = ""

    for call in batch.calls:
        if is_stale and is_stale():
            break
        name = call.name
        tool_args = dict(call.args)
        spoken = get_tool_fallback(name)
        tool_payload: dict[str, Any] = {"status": "error", "spoken": spoken}

        if not user_id:
            spoken = "No identifiqué al usuario, señor."
            tool_payload = {"status": "error", "spoken": spoken}
        else:
            try:
                tool_result = await asyncio.wait_for(
                    execute_voice_tool(name, user_id, tool_args),
                    timeout=tool_timeout_sec(name),
                )
                if build_tool_payload:
                    spoken, tool_payload = build_tool_payload(name, tool_args, tool_result)
                elif tool_result.get("ok") is False:
                    spoken = str(
                        tool_result.get("spoken") or get_tool_fallback(name)
                    )
                    tool_payload = {
                        "status": "error",
                        "spoken": spoken,
                        "error": tool_result.get("error"),
                    }
                else:
                    spoken = str(tool_result.get("spoken") or "Completado, señor.")
                    tool_payload = {"status": "success", "spoken": spoken}
            except asyncio.TimeoutError:
                logger.warning("[TOOL:ASYNC] timeout name=%s user=%s", name, (user_id or "?")[:8])
                if name == "search_web" and batch.on_web_fallback:
                    batch.on_web_fallback()
                spoken = (
                    "Señor, tardó demasiado. ¿Intento de nuevo?"
                    if name != "search_web"
                    else get_tool_fallback("search_web")
                )
                tool_payload = {"status": "timeout", "spoken": spoken}
            except Exception:
                logger.exception("[TOOL:ASYNC] error name=%s user=%s", name, (user_id or "?")[:8])
                spoken = get_tool_fallback(name)
                tool_payload = {"status": "error", "spoken": spoken}

        results.append((name, tool_payload, spoken))
        if spoken:
            final_spoken = spoken

    if is_stale and is_stale():
        return results

    if final_spoken:
        try:
            await deliver(final_spoken)
        except Exception:
            logger.exception("[TOOL:ASYNC] deliver failed user=%s", (user_id or "?")[:8])

    return results


def format_search_web_spoken(
    tool_args: dict[str, Any],
    tool_result: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    from app.services.gemini_voice_llm import GeminiVoiceLlm

    if tool_result.get("fallback") or tool_result.get("status") == "timeout":
        spoken, payload = GeminiVoiceLlm._search_web_tool_payload(tool_result)
        return spoken, payload
    spoken, payload = GeminiVoiceLlm._search_web_tool_payload(tool_result)
    if payload.get("status") == "success" and spoken:
        kind = str(tool_args.get("kind") or "general")
        spoken = format_web_delivery(kind, spoken)
        payload = {**payload, "spoken": spoken}
    return spoken, payload
