"""Modo de prueba aislado para voz — activable por env, sin tocar prod Llama/orquestador."""

from __future__ import annotations

from app.config import get_settings

GEMINI_STANDALONE_MODE = "gemini_standalone"

GEMINI_STANDALONE_SYSTEM = """
Eres CED, asistente de voz personal del Castillo Evolución Digital.
Tono formal y cercano — trata al usuario como "señor".

Este turno es charla casual o desahogo personal. No hay herramientas, búsquedas web,
módulos ni tareas en curso. Responde de inmediato con el texto final.

Instrucciones:
- 1-2 oraciones completas, empáticas y directas — máximo ~320 tokens de salida.
- Valida lo que comparte antes de aconsejar, si aplica.
- Responde ya: PROHIBIDO frases de espera ("un momento", "permítame", "deme un segundo",
  "voy a buscar", "consulto", "investigo" o variantes).
- PROHIBIDO prometer acciones, tools, internet o invocar funciones.
- PROHIBIDO "¿En qué puedo ayudarle?" u otras respuestas transaccionales vacías.
""".strip()


def voice_test_mode() -> str:
    return (get_settings().voice_test_mode or "").strip().lower()


def is_gemini_standalone_voice_test() -> bool:
    return voice_test_mode() == GEMINI_STANDALONE_MODE


def voice_standalone_modules() -> frozenset[str]:
    """Módulos del orquestador permitidos en modo standalone (VOICE_STANDALONE_MODULES)."""
    if not is_gemini_standalone_voice_test():
        return frozenset()
    raw = (get_settings().voice_standalone_modules or "").strip()
    if not raw:
        return frozenset()
    return frozenset(part.strip().lower() for part in raw.split(",") if part.strip())


def is_standalone_module_enabled(module: str) -> bool:
    name = (module or "").strip().lower()
    return bool(name) and name in voice_standalone_modules()


def resolve_standalone_forced_module(
    user_text: str,
    transcript: list,
    *,
    call_id: str,
    user_id: str,
) -> str | None:
    """Ancla estricta o módulo activo — solo si está en VOICE_STANDALONE_MODULES."""
    enabled = voice_standalone_modules()
    if not enabled:
        return None

    from app.services.ced_orchestrator import (
        detect_strict_intent_v2,
        get_orchestrator,
        is_module_command,
    )

    strict = detect_strict_intent_v2(user_text)
    if strict and strict in enabled:
        return strict

    orch = get_orchestrator(call_id)
    active = (orch.active_module or "").strip().lower()
    if active and active in enabled:
        if is_module_command(user_text, active, transcript, user_id=user_id):
            return active

    return None
