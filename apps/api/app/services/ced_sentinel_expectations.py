"""Contrato operativo de CED — lo que Centinela usa para auditar el sistema."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# Referencia para /admin/sentinel y bitácora; no sustituye docs de producto.
SYSTEM_EXPECTATIONS: list[dict[str, str]] = [
    {
        "id": "voice_default",
        "title": "Voz en producción",
        "body": (
            "Web usa Retell Native Pilot por defecto (register-call-native-pilot). "
            "Retell ejecuta el LLM del panel + TTS Jarvis; las tools son HTTP POST "
            "a API_PUBLIC_URL/v1/retell/tools/{nombre}. Custom LLM (WebSocket Claude) "
            "solo con ?voicePilot=custom — no es el camino normal."
        ),
    },
    {
        "id": "voice_brain",
        "title": "Cerebro conversacional (voz)",
        "body": (
            "En Native Pilot el modelo lo fija el LLM de Retell (agente staging). "
            "El bootstrap del API puede sincronizar retell_native_pilot_model "
            "(default código: Claude Haiku 4.5/5.5 según config). "
            "Custom LLM usa retell_llm_provider=claude y anthropic_model_retell_llm."
        ),
    },
    {
        "id": "analyze_not_generate",
        "title": "Foto + Analizar = duda, no PNG",
        "body": (
            "Si el usuario elige Analizar al subir una foto (o pregunta cómo se hace "
            "eso que se ve), CED explica y Centinela bloquea generate_image / "
            "generate_image_with_reference. Editar, Variar o «hazme un flyer» sí generan."
        ),
    },
    {
        "id": "voice_history",
        "title": "Historial de voz",
        "body": (
            "Piloto nativo: el transcript se persiste en call_ended/call_analyzed "
            "(webhook Retell → persist_retell_call_transcript). Custom LLM también "
            "append por turno. Historial → mismo hilo que el chat."
        ),
    },
    {
        "id": "voice_tools",
        "title": "Tools de voz",
        "body": (
            "37 funciones nativas: clima, web, YouTube, imagen, PDF, Meta, prospección, "
            "mapa, finanzas, cámara, avanzado, oportunidades, etc. Cada una tiene ruta "
            "dedicada en retell.py; el HUD recibe eventos vía sesión voz del cliente."
        ),
    },
    {
        "id": "chat_brain",
        "title": "Chat de texto",
        "body": (
            "Conversación principal con Gemini (gemini_voice_model / 2.5 Flash). "
            "Modo avanzado: Claude. Imágenes y visión: Gemini. FitLine: conocimiento "
            "interno antes que Tavily."
        ),
    },
    {
        "id": "sentinel_role",
        "title": "Rol del Centinela",
        "body": (
            "Imagen: Centinela revisa SIEMPRE el brief vs el pedido y, si hay fondo/colores/"
            "copy literal, hace QA visual con Gemini Flash tras generar; un reintento si falla. "
            "Sin guardia admin para imagen. Con guardia ON: sondas, bitácora, PDF, "
            "«Corrigiendo datos…» en pantalla."
        ),
    },
]


def voice_stack_report() -> dict[str, str]:
    """Resumen legible de qué motor usa cada superficie (env + defaults)."""
    from app.config import get_settings

    s = get_settings()
    standalone = (s.voice_test_mode or "").strip().lower() == "gemini_standalone"
    custom_default = (s.retell_llm_provider or "claude").strip().lower()

    if standalone and (not s.is_production or s.voice_standalone_allow_prod):
        voice_path = "Retell → Gemini standalone (sin orquestador CED)"
    else:
        voice_path = "Retell Native Pilot (LLM + tools en Retell → API CED)"

    return {
        "voz_conversacion": (
            f"{voice_path}. Panel Retell define el LLM en llamada; "
            f"ref. bootstrap API: {s.retell_native_pilot_model.strip() or '—'}. "
            "Gemini NO corre en segundo plano en la llamada; solo se usa al invocar "
            "generate_image (o chat/imagen aparte)."
        ),
        "voz_custom_llm_opcional": (
            f"Custom LLM: {custom_default} ({s.anthropic_model_retell_llm}) "
            "solo si el cliente usa ?voicePilot=custom."
        ),
        "chat_texto": f"Gemini ({s.gemini_voice_model.strip() or 'gemini-2.5-flash'}).",
        "modo_avanzado": f"Claude ({s.anthropic_model_retell_llm}).",
        "imagenes": (
            f"Gemini ({s.gemini_image_model}) + ChatGPT Image si hay OPENAI_API_KEY; "
            "Ideogram desactivado."
        ),
    }


def audit_voice_tools_parity() -> dict[str, Any]:
    """Comprueba que build_native_pilot_tools coincide con rutas HTTP."""
    from app.services.retell_native_pilot import build_native_pilot_tools

    tools = {t["name"] for t in build_native_pilot_tools(api_public_url="https://audit.local")}
    retell_py = Path(__file__).resolve().parents[1] / "routers" / "retell.py"
    text = retell_py.read_text(encoding="utf-8")
    routes = set(re.findall(r'@router\.post\("/tools/([^"/{]+)"', text))
    missing_routes = sorted(tools - routes)
    extra_routes = sorted(routes - tools - {"{tool_name}"})
    ok = not missing_routes and not extra_routes
    return {
        "ok": ok,
        "tool_count": len(tools),
        "route_count": len(routes),
        "missing_routes": missing_routes,
        "extra_routes": extra_routes,
    }


def audit_voice_pilot_config() -> dict[str, Any]:
    from app.config import get_settings

    s = get_settings()
    issues: list[str] = []
    watches: list[str] = []

    if not s.retell_api_key.strip():
        issues.append("RETELL_API_KEY vacía")
    if not s.retell_native_staging_agent_id.strip():
        watches.append("RETELL_NATIVE_STAGING_AGENT_ID (piloto nativo)")
    if not s.retell_native_staging_llm_id.strip():
        watches.append("RETELL_NATIVE_STAGING_LLM_ID")
    pub = s.api_public_url.strip()
    if not pub or pub.startswith("http://localhost"):
        issues.append("API_PUBLIC_URL no es URL pública (Retell no alcanza tools)")
    if not s.retell_webhook_secret.strip():
        watches.append("RETELL_WEBHOOK_SECRET (firma tools)")
    mode = (s.voice_test_mode or "").strip().lower()
    if mode == "gemini_standalone" and s.is_production and not s.voice_standalone_allow_prod:
        watches.append("VOICE_TEST_MODE=gemini_standalone ignorado en prod (OK)")
    elif mode == "gemini_standalone":
        watches.append("VOICE_TEST_MODE=gemini_standalone activo — sin tools CED")

    level = "error" if issues else ("watch" if watches else "ok")
    detail_parts = []
    if issues:
        detail_parts.append("Crítico: " + "; ".join(issues))
    if watches:
        detail_parts.append("Revisar: " + "; ".join(watches))
    if not detail_parts:
        detail_parts.append("Claves piloto y URL pública presentes.")

    return {
        "level": level,
        "title": "Piloto de voz" if level != "error" else "Piloto de voz incompleto",
        "detail": " ".join(detail_parts)[:400],
        "issues": issues,
        "watches": watches,
    }
