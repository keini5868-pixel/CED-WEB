"""Límites y recorte de texto para narración por voz (Retell / ElevenLabs)."""

from __future__ import annotations

import re

# Retell tolera ~60–90 s de TTS; 720 chars ≈ 45–55 s en español.
VOICE_SPOKEN_MAX_CHARS = 720
VOICE_ADVISORY_MAX_CHARS = 1100

_ADVISORY_HINTS = re.compile(
    r"\b("
    r"video|demo|demostrar|mostrar|guion|guión|script|segundos|relevante|"
    r"estrategia|presentar|pitch|contenido|grabar|pantalla|secuencia|seq"
    r")\b",
    re.I,
)


def is_advisory_voice_query(text: str) -> bool:
    """Preguntas creativas/estratégicas que necesitan respuesta más larga en voz."""
    cleaned = " ".join((text or "").split()).strip()
    if len(cleaned) < 20:
        return False
    return bool(_ADVISORY_HINTS.search(cleaned))


def voice_spoken_limit(text: str) -> int:
    return VOICE_ADVISORY_MAX_CHARS if is_advisory_voice_query(text) else VOICE_SPOKEN_MAX_CHARS


def fit_voice_spoken(text: str, *, max_chars: int | None = None) -> str:
    """Recorta al límite de voz sin cortar a mitad de oración cuando es posible."""
    cleaned = " ".join((text or "").split()).strip()
    if not cleaned:
        return ""
    limit = max_chars if max_chars is not None else voice_spoken_limit(cleaned)
    if len(cleaned) <= limit:
        return cleaned

    chunk = cleaned[:limit]
    last_end = max(chunk.rfind(". "), chunk.rfind("! "), chunk.rfind("? "))
    if last_end >= int(limit * 0.45):
        return chunk[: last_end + 1].strip()

    last_space = chunk.rfind(" ")
    if last_space >= int(limit * 0.55):
        return f"{chunk[:last_space].strip()}."
    return f"{chunk.strip()}."
