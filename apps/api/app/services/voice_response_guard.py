"""Filtro defensivo — bloquea fugas de código, tools y KB interno en respuestas de voz."""

from __future__ import annotations

import re

from app.services.internal_kb_guard import (
    contains_internal_kb_leak,
    strip_internal_kb_from_reply,
)
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


_INFRA_ALWAYS = re.compile(
    r"(?i)\b(?:railway|supabase|retell|cartesia|nano\s*banana|livekit|"
    r"ideogram|tavily|elevenlabs|ollama|anthropic)\b"
)
_VENDOR_CLAIM = re.compile(
    r"(?is)\b(?:uso|usamos|estoy\s+(?:hecho|basad[oa]|construid[oa]|entrenad[oa])|"
    r"me\s+(?:potencia|impulsa|corre)|mi\s+(?:modelo|motor|proveedor|"
    r"infraestructura|backend|servidor)|powered\s+by|corro\s+en|"
    r"hosteado|alojado\s+en|la\s+api\s+de|el\s+modelo\s+(?:es|que\s+uso))"
    r".{0,56}"
    r"(?:gemini|claude|openai|gpt-?\s*4|llama|google\s+ai|vertex)"
)


def contains_stack_leak(text: str) -> bool:
    cleaned = (text or "").strip()
    if not cleaned:
        return False
    return bool(_INFRA_ALWAYS.search(cleaned) or _VENDOR_CLAIM.search(cleaned))


def strip_stack_leak(text: str) -> str:
    """Quita frases que revelan proveedores/infra; si no queda nada, negativa fija."""
    from app.domain.ced_identity import CED_STACK_REFUSAL

    raw = (text or "").strip()
    if not raw or not contains_stack_leak(raw):
        return raw
    parts = re.split(r"(?<=[.!?…])\s+", raw)
    kept = [p for p in parts if p.strip() and not contains_stack_leak(p)]
    out = " ".join(kept).strip()
    return out or CED_STACK_REFUSAL


def guard_voice_response(text: str) -> tuple[str, bool]:
    """Devuelve (texto_seguro, fue_bloqueado)."""
    cleaned = normalize_numbers_for_speech(" ".join((text or "").split()).strip())
    if not cleaned:
        return "", False
    if contains_code_leak(cleaned) or contains_tool_leak(cleaned):
        return "", True
    if contains_internal_kb_leak(cleaned):
        stripped = strip_internal_kb_from_reply(cleaned)
        if stripped and not contains_internal_kb_leak(stripped):
            cleaned = stripped
        else:
            return "", True
    if contains_stack_leak(cleaned):
        cleaned = strip_stack_leak(cleaned)
    return cleaned, False
