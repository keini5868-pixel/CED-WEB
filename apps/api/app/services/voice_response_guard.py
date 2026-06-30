"""Filtro defensivo — bloquea fugas de código y tool calls en respuestas de voz."""

from __future__ import annotations

import re

from app.services.voice_spoken import normalize_numbers_for_speech

_CODE_LEAK = re.compile(
    r"(?:"
    r"tool_code|end_of_tool_code|"
    r"print\s*\(|"
    r"\bdef\s+\w+\s*\(|"
    r"```|"
    r"import\s+\w+|"
    r"function\s+\w+\s*\("
    r")",
    re.IGNORECASE,
)

_TOOL_NAMED_ARG = re.compile(r"\b[a-z_][a-z0-9_]*\s*\(\s*[a-z_]+\s*=", re.IGNORECASE)
_TOOL_SNAKE_CALL = re.compile(r"\b[a-z_][a-z0-9_]*(?:_[a-z0-9_]+)+\s*\(", re.IGNORECASE)
_TOOL_INVOKE_ONLY = re.compile(r"^[a-z_][a-z0-9_]*\s*\([^)]*\)\s*\.?$", re.IGNORECASE)
_TOOL_PARTIAL = re.compile(r"\b[a-z_]{4,}(?:_\w+)+\s*\(?$", re.IGNORECASE)
_TOOL_EMBEDDED = re.compile(
    r"\b(?:buscar_|publicar_|generate_|analyze_|consultar_|request_|activar_|desactivar_|"
    r"leer_|recall_|save_)[a-z0-9_]*\s*\(",
    re.IGNORECASE,
)


def contains_code_leak(text: str) -> bool:
    cleaned = (text or "").strip()
    if not cleaned:
        return False
    return bool(_CODE_LEAK.search(cleaned))


def contains_tool_leak(text: str) -> bool:
    cleaned = " ".join((text or "").split()).strip()
    if not cleaned:
        return False
    return bool(
        _TOOL_NAMED_ARG.search(cleaned)
        or _TOOL_SNAKE_CALL.search(cleaned)
        or _TOOL_INVOKE_ONLY.match(cleaned)
        or _TOOL_PARTIAL.search(cleaned)
        or _TOOL_EMBEDDED.search(cleaned)
    )


def guard_voice_response(text: str) -> tuple[str, bool]:
    """Devuelve (texto_seguro, fue_bloqueado)."""
    cleaned = normalize_numbers_for_speech(" ".join((text or "").split()).strip())
    if not cleaned:
        return "", False
    if contains_code_leak(cleaned) or contains_tool_leak(cleaned):
        return "", True
    return cleaned, False
