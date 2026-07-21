"""Modo de prueba aislado para voz — activable por env, sin tocar prod Llama/orquestador."""

from __future__ import annotations

import logging

from app.config import get_settings

logger = logging.getLogger(__name__)

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
    """True solo cuando el modo prueba está activo de forma segura.

    En production, `VOICE_TEST_MODE=gemini_standalone` se ignora a menos que
    `VOICE_STANDALONE_ALLOW_PROD=true`. Sin tools, imagen/PDF/Gmail fallan con
    mensajes inventados del LLM ("inténtalo más tarde") aunque Gemini Image sí
    funcione por chat — regresión observada 2026-07.
    """
    if voice_test_mode() != GEMINI_STANDALONE_MODE:
        return False
    settings = get_settings()
    if settings.is_production() and not bool(settings.voice_standalone_allow_prod):
        logger.error(
            "[VOICE] VOICE_TEST_MODE=gemini_standalone IGNORADO en production "
            "(deja la voz sin tools). Quite VOICE_TEST_MODE o ponga "
            "VOICE_STANDALONE_ALLOW_PROD=true solo para staging deliberado."
        )
        return False
    return True


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
    """Ancla estricta, heurística ambiente (capa 3) o módulo activo — standalone only.

    Nota fases futuras: calendario/finanzas/Gmail deberían añadir clasificador Gemini
    condicionado (capa 4) ante mayor costo de falsos positivos — no aplica a clima.
    """
    enabled = voice_standalone_modules()
    if not enabled:
        return None

    from app.services.ced_orchestrator import (
        detect_strict_intent_v2,
        get_orchestrator,
        is_module_command,
    )
    from app.modules.environment_module import (
        environment_awaiting_location_followup,
        is_environment_action_request,
        is_environment_location_followup,
        recent_environment_user_query,
    )

    strict = detect_strict_intent_v2(user_text)
    if strict and strict in enabled:
        return strict

    if "environment" in enabled:
        if is_environment_action_request(user_text):
            return "environment"
        if (
            is_environment_location_followup(user_text)
            and recent_environment_user_query(transcript, exclude=user_text)
            and environment_awaiting_location_followup(transcript, exclude=user_text)
        ):
            return "environment"

    orch = get_orchestrator(call_id)
    active = (orch.active_module or "").strip().lower()
    if active and active in enabled:
        if is_module_command(user_text, active, transcript, user_id=user_id):
            return active

    return None


def standalone_environment_query(user_text: str, transcript: list) -> str:
    """Texto efectivo para orquestador ambiente (follow-up de ubicación incluido)."""
    from app.modules.environment_module import compose_environment_query

    return compose_environment_query(user_text, transcript)


def standalone_user_keys_overlap(a: str, b: str, *, min_prefix: int = 12) -> bool:
    """True si dos claves de turno parecen la misma frase (STT parcial vs final)."""
    left = (a or "").strip().lower()
    right = (b or "").strip().lower()
    if not left or not right:
        return False
    if left == right:
        return True
    shorter, longer = (left, right) if len(left) <= len(right) else (right, left)
    if len(shorter) >= min_prefix and longer.startswith(shorter):
        return True
    if len(shorter) >= 8 and shorter in longer:
        return True
    return False
