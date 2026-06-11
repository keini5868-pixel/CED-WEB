"""Configuración OpenAI Realtime — voces y parámetros de sesión WebRTC."""

from __future__ import annotations

from typing import Any

OPENAI_VOICES = frozenset({"alloy", "ash", "ballad", "coral", "echo", "sage", "shimmer", "verse"})
DEFAULT_OPENAI_VOICE = "alloy"

REALTIME_MAX_OUTPUT_TOKENS = 200
REALTIME_TEMPERATURE = 0.8

# WebRTC + semantic VAD (docs OpenAI Realtime VAD guide)
REALTIME_TURN_DETECTION: dict[str, Any] = {
    "type": "semantic_vad",
    "eagerness": "medium",
    "create_response": True,
    "interrupt_response": True,
}

REALTIME_TURN_DETECTION_FALLBACK: dict[str, Any] = {
    "type": "server_vad",
    "threshold": 0.6,
    "prefix_padding_ms": 300,
    "silence_duration_ms": 800,
    "create_response": True,
    "interrupt_response": True,
}

REALTIME_NOISE_REDUCTION: dict[str, str] = {"type": "near_field"}


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
