"""Configuración OpenAI Realtime — voces y parámetros de sesión WebRTC."""

from __future__ import annotations

from typing import Any

OPENAI_VOICES = frozenset({"alloy", "ash", "ballad", "coral", "echo", "sage", "shimmer", "verse"})
DEFAULT_OPENAI_VOICE = "alloy"

REALTIME_MAX_OUTPUT_TOKENS = 120
REALTIME_TEMPERATURE = 0.72

# semantic_vad high = respuesta más rápida (menos espera al usuario)
REALTIME_TURN_DETECTION: dict[str, Any] = {
    "type": "semantic_vad",
    "eagerness": "high",
    "create_response": True,
    "interrupt_response": True,
}

REALTIME_TURN_DETECTION_FALLBACK: dict[str, Any] = {
    "type": "server_vad",
    "threshold": 0.55,
    "prefix_padding_ms": 200,
    "silence_duration_ms": 500,
    "create_response": True,
    "interrupt_response": True,
}

REALTIME_NOISE_REDUCTION: dict[str, str] = {"type": "near_field"}


def profile_for_response_speed(speed: str | None) -> tuple[float, dict[str, Any]]:
    """Temperatura y turn_detection según preferencia de velocidad."""
    key = (speed or "balanced").strip().lower()
    if key == "fast":
        return 0.65, {**REALTIME_TURN_DETECTION, "eagerness": "high"}
    if key == "thoughtful":
        return 0.78, {**REALTIME_TURN_DETECTION, "eagerness": "low"}
    return REALTIME_TEMPERATURE, REALTIME_TURN_DETECTION


def normalize_openai_voice(name: str | None) -> str:
    v = (name or DEFAULT_OPENAI_VOICE).strip().lower()
    if v in OPENAI_VOICES:
        return v
    legacy = {
        "charon": "echo",
        "kore": "shimmer",
        "fenrir": "ash",
        "aoede": "coral",
        "puck": "ballad",
    }
    return legacy.get(v, DEFAULT_OPENAI_VOICE)
