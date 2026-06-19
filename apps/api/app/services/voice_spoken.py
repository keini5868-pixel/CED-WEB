"""Límites y recorte de texto para narración por voz (Retell / ElevenLabs)."""

from __future__ import annotations

import re

# Retell tolera ~60–90 s de TTS; 720 chars ≈ 45–55 s en español.
VOICE_SPOKEN_MAX_CHARS = 720

_SENTENCE_END = re.compile(r"[.!?…]\s+")


def fit_voice_spoken(text: str, *, max_chars: int = VOICE_SPOKEN_MAX_CHARS) -> str:
    """Recorta al límite de voz sin cortar a mitad de oración cuando es posible."""
    cleaned = " ".join((text or "").split()).strip()
    if not cleaned:
        return ""
    if len(cleaned) <= max_chars:
        return cleaned

    chunk = cleaned[:max_chars]
    last_end = max(chunk.rfind(". "), chunk.rfind("! "), chunk.rfind("? "))
    if last_end >= int(max_chars * 0.45):
        return chunk[: last_end + 1].strip()

    last_space = chunk.rfind(" ")
    if last_space >= int(max_chars * 0.55):
        return f"{chunk[:last_space].strip()}."
    return f"{chunk.strip()}."
