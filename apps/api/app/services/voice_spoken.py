"""Límites y recorte de texto para narración por voz (Retell / ElevenLabs)."""

from __future__ import annotations

import re

# Retell ~60–90 s por bloque; repartimos en 2–3 bloques secuenciales sin perder texto.
VOICE_SPOKEN_MAX_CHARS = 720
VOICE_ADVISORY_MAX_CHARS = 1800
VOICE_NEWS_MAX_CHARS = 2000
VOICE_CHUNK_TARGET = 680

_ADVISORY_HINTS = re.compile(
    r"\b("
    r"video|demo|demostrar|mostrar|guion|guión|script|segundos|relevante|"
    r"estrategia|presentar|pitch|contenido|grabar|pantalla|secuencia|seq"
    r")\b",
    re.I,
)

_THOUSANDS_COMMA_RE = re.compile(r"\d{1,3}(?:,\d{3})+")
_SENTENCE_END_RE = re.compile(r'[.!?…]["\']?$')


def normalize_numbers_for_speech(text: str) -> str:
    """Quita separadores de miles para que el TTS pronuncie cantidades, no dígitos sueltos."""
    cleaned = text or ""
    if not cleaned:
        return ""
    cleaned = _THOUSANDS_COMMA_RE.sub(lambda m: m.group(0).replace(",", ""), cleaned)
    cleaned = re.sub(r"(\d),(\d{1,2})\b", r"\1.\2", cleaned)
    return cleaned


def is_advisory_voice_query(text: str) -> bool:
    """Preguntas creativas/estratégicas que necesitan respuesta más larga en voz."""
    cleaned = " ".join((text or "").split()).strip()
    if len(cleaned) < 20:
        return False
    return bool(_ADVISORY_HINTS.search(cleaned))


def voice_spoken_limit(text: str) -> int:
    return VOICE_ADVISORY_MAX_CHARS if is_advisory_voice_query(text) else VOICE_SPOKEN_MAX_CHARS


def chunk_ends_with_punctuation(text: str) -> bool:
    cleaned = (text or "").strip()
    return bool(cleaned and _SENTENCE_END_RE.search(cleaned))


def fit_voice_spoken(text: str, *, max_chars: int | None = None) -> str:
    """Recorta al límite de voz sin cortar a mitad de oración cuando es posible."""
    cleaned = normalize_numbers_for_speech(" ".join((text or "").split()).strip())
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


def _find_phrase_break(text: str, max_len: int) -> int:
    """Índice de corte preferido: oración completa, coma, o límite de palabra."""
    if len(text) <= max_len:
        return len(text)
    chunk = text[:max_len]
    min_sentence = int(max_len * 0.35)
    last_end = max(chunk.rfind(". "), chunk.rfind("! "), chunk.rfind("? "))
    if last_end >= min_sentence:
        return last_end + 1

    comma_idx = chunk.rfind(", ")
    if comma_idx >= int(max_len * 0.40):
        return comma_idx + 1

    last_space = chunk.rfind(" ")
    if last_space >= int(max_len * 0.50):
        return last_space

    return max_len


def _split_long_phrase(phrase: str, max_chunk: int) -> list[str]:
    """Parte frases largas en unidades gramaticales (oración o sub-oración con coma)."""
    cleaned = phrase.strip()
    if not cleaned:
        return []
    if len(cleaned) <= max_chunk:
        return [cleaned]

    parts: list[str] = []
    remaining = cleaned
    while remaining:
        if len(remaining) <= max_chunk:
            parts.append(remaining)
            break
        cut = _find_phrase_break(remaining, max_chunk)
        if cut <= 0:
            cut = max_chunk
        piece = remaining[:cut].strip()
        if piece:
            if not chunk_ends_with_punctuation(piece) and not piece.endswith(","):
                piece = f"{piece}."
            parts.append(piece)
        remaining = remaining[cut:].strip()
    return parts or [cleaned[:max_chunk].rstrip()]


def split_voice_delivery_chunks(
    text: str,
    *,
    max_chunk: int = VOICE_CHUNK_TARGET,
) -> list[tuple[str, bool]]:
    """Parte texto largo en bloques por oraciones — sin cortar a mitad de cláusula."""
    cleaned = normalize_numbers_for_speech(" ".join((text or "").split()).strip())
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
            chunks.extend(_split_long_phrase(sent, max_chunk))
            current = ""
        else:
            current = sent
    if current:
        chunks.append(current)

    if len(chunks) > 3:
        tail = " ".join(chunks[2:])
        chunks = [chunks[0], chunks[1], *_split_long_phrase(tail, max_chunk)]

    return [(part, idx == len(chunks) - 1) for idx, part in enumerate(chunks)]
