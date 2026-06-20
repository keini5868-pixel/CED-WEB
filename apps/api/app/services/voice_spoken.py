"""Límites y recorte de texto para narración por voz (Retell / ElevenLabs)."""

from __future__ import annotations

import re

# Retell ~60–90 s por bloque; repartimos en 2–3 bloques secuenciales sin perder texto.
VOICE_SPOKEN_MAX_CHARS = 720
VOICE_ADVISORY_MAX_CHARS = 1800
VOICE_NEWS_MAX_CHARS = 1500
VOICE_CHUNK_TARGET = 680

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



def _split_long_sentence(sent: str, max_chunk: int) -> list[str]:
    """Parte oraciones largas por palabras completas."""
    cleaned = sent.strip()
    if len(cleaned) <= max_chunk:
        return [cleaned]
    words = cleaned.split()
    parts: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip() if current else word
        if len(candidate) <= max_chunk:
            current = candidate
            continue
        if current:
            parts.append(current)
        current = word
    if current:
        parts.append(current)
    return parts or [cleaned[:max_chunk].rstrip()]


def split_voice_delivery_chunks(
    text: str,
    *,
    max_chunk: int = VOICE_CHUNK_TARGET,
) -> list[tuple[str, bool]]:
    """Parte texto largo en bloques por oraciones — sin descartar el final."""
    cleaned = " ".join((text or "").split()).strip()
    if not cleaned:
        return []
    if len(cleaned) <= max_chunk:
        return [(cleaned, True)]

    sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    sentences = [s.strip() for s in sentences if s.strip()]
    if not sentences:
        return [(cleaned, True)]

    chunks: list[str] = []
    current = ""
    for sent in sentences:
        candidate = f"{current} {sent}".strip() if current else sent
        if len(candidate) <= max_chunk:
            current = candidate
            continue
        if current:
            chunks.append(current)
        if len(sent) > max_chunk:
            chunks.extend(_split_long_sentence(sent, max_chunk))
        else:
            current = sent
    if current:
        chunks.append(current)

    if len(chunks) > 3:
        tail = " ".join(chunks[2:])
        chunks = [chunks[0], chunks[1], tail]

    return [(part, idx == len(chunks) - 1) for idx, part in enumerate(chunks)]
