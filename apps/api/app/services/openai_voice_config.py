"""Configuración OpenAI Realtime — voces y parámetros."""

from __future__ import annotations

OPENAI_VOICES = frozenset({"alloy", "ash", "ballad", "coral", "echo", "sage", "shimmer", "verse"})
DEFAULT_OPENAI_VOICE = "alloy"

REALTIME_MAX_OUTPUT_TOKENS = 150
REALTIME_TEMPERATURE = 0.8


def normalize_openai_voice(name: str | None) -> str:
    v = (name or DEFAULT_OPENAI_VOICE).strip().lower()
    if v in OPENAI_VOICES:
        return v
    # Mapeo legacy Gemini → OpenAI
    legacy = {
        "charon": "echo",
        "kore": "shimmer",
        "fenrir": "ash",
        "aoede": "coral",
        "puck": "ballad",
    }
    return legacy.get(v, DEFAULT_OPENAI_VOICE)
