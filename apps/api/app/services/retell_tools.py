"""Custom functions Retell — mapeo de las 19 tools CED."""

from __future__ import annotations

from typing import Any

from app.config import get_settings
from app.services.openai_voice_tools import OPENAI_REALTIME_TOOLS

EXECUTION_MESSAGES: dict[str, str] = {
    "search_web": "Consultando, señor",
    "consultar_claude": "Ejecutando análisis profundo, señor",
    "generate_image": "Generando imagen, señor",
    "generate_image_with_reference": "Generando imagen, señor",
    "save_memory": "Un momento, señor",
    "recall_memory": "Consultando memoria, señor",
    "recall_previous_conversations": "Consultando conversaciones, señor",
    "save_to_long_term_memory": "Un momento, señor",
    "request_camera_activation": "Activando cámara, señor",
    "request_camera_deactivation": "Desactivando cámara, señor",
    "analyze_camera_frame": "Analizando, señor",
    "buscar_lo_visible": "Consultando, señor",
    "generar_pdf": "Generando documento, señor",
    "leer_comentarios_redes": "Consultando, señor",
    "activar_prospeccion": "Activando, señor",
    "desactivar_prospeccion": "Desactivando, señor",
    "reporte_prospeccion": "Consultando reporte, señor",
    "publicar_facebook": "Un momento, señor",
    "publicar_instagram": "Un momento, señor",
    "activar_modo_conducir": "Abriendo mapa, señor",
    "buscar_direccion": "Buscando dirección, señor",
    "iniciar_navegacion": "Calculando ruta, señor",
    "cancelar_navegacion": "Un momento, señor",
    "estado_navegacion": "Consultando ruta, señor",
}

TIMEOUT_MS: dict[str, int] = {
    "generate_image": 60_000,
    "generate_image_with_reference": 60_000,
    "consultar_claude": 30_000,
    "generar_pdf": 20_000,
    "search_web": 20_000,
    "publicar_facebook": 35_000,
    "publicar_instagram": 35_000,
    "leer_comentarios_redes": 8_000,
    "activar_prospeccion": 5_000,
    "desactivar_prospeccion": 5_000,
    "reporte_prospeccion": 8_000,
    "save_memory": 5_000,
    "recall_memory": 5_000,
    "recall_previous_conversations": 8_000,
    "save_to_long_term_memory": 5_000,
    "buscar_direccion": 12_000,
    "iniciar_navegacion": 20_000,
    "activar_modo_conducir": 5_000,
    "cancelar_navegacion": 5_000,
    "estado_navegacion": 5_000,
    "request_camera_activation": 12_000,
    "request_camera_deactivation": 5_000,
    "analyze_camera_frame": 45_000,
    "analyze_uploaded_image": 30_000,
    "buscar_lo_visible": 45_000,
}


def _tool_base_url() -> str:
    return get_settings().api_public_url.rstrip("/")


def openai_tool_to_retell(tool: dict[str, Any]) -> dict[str, Any]:
    name = str(tool.get("name") or "")
    params = tool.get("parameters") or {"type": "object", "properties": {}, "required": []}
    return {
        "type": "custom",
        "name": name,
        "description": str(tool.get("description") or name),
        "url": f"{_tool_base_url()}/v1/retell/tools/{name}",
        "method": "POST",
        "parameters": params,
        "speak_during_execution": True,
        "speak_after_execution": True,
        "execution_message_description": EXECUTION_MESSAGES.get(name, "Un momento, señor"),
        "timeout_ms": TIMEOUT_MS.get(name, 10_000),
    }


def build_retell_general_tools() -> list[dict[str, Any]]:
    return [openai_tool_to_retell(t) for t in OPENAI_REALTIME_TOOLS if t.get("name")]
