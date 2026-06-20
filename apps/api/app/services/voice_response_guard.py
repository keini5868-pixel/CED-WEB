"""Filtro defensivo — bloquea fugas de código (tool_code, print, etc.) en respuestas de voz."""

from __future__ import annotations

import re

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


def contains_code_leak(text: str) -> bool:
    cleaned = (text or "").strip()
    if not cleaned:
        return False
    return bool(_CODE_LEAK.search(cleaned))


def guard_voice_response(text: str) -> tuple[str, bool]:
    """Devuelve (texto_seguro, fue_bloqueado)."""
    cleaned = " ".join((text or "").split()).strip()
    if not cleaned:
        return "", False
    if contains_code_leak(cleaned):
        return "", True
    return cleaned, False
