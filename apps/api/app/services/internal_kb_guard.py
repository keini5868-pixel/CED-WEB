"""Detección y limpieza de fugas del bloque interno de conocimiento CED."""

from __future__ import annotations

import re

INTERNAL_KB_LEAK_PATTERNS = (
    "Conocimiento interno CED",
    "[Marketing digital]",
    "[Finanzas personales]",
    "[general]",
    "priorizar sobre suposiciones",
)

_INTERNAL_KB_LEAK_RE = re.compile(
    r"Conocimiento interno CED\s*\(priorizar",
    re.I,
)

VOICE_KB_LEAK_OVERLAY = """
Tu respuesta anterior incluyó texto interno del sistema (Conocimiento interno CED o etiquetas [Marketing digital]).
Ese bloque es SOLO contexto interno — NUNCA debe oírse ni leerse al usuario.
Reescribe de forma natural y útil, usando el conocimiento sin citar ni copiar el formato interno.
""".strip()


def contains_internal_kb_leak(text: str) -> bool:
    """True si la respuesta expone el bloque interno de KB al usuario."""
    t = (text or "").strip()
    if not t:
        return False
    if _INTERNAL_KB_LEAK_RE.search(t):
        return True
    if any(pattern in t for pattern in INTERNAL_KB_LEAK_PATTERNS):
        return True
    if re.search(r"Conocimiento interno CED", t, re.I) and re.search(
        r"-\s*\[[^\]]+\]\s+[^:]+:\s",
        t,
    ):
        return True
    return False


def strip_internal_kb_from_reply(text: str) -> str:
    """Elimina bloques de KB filtrados que el modelo copió a la respuesta."""
    cleaned = re.sub(
        r"Conocimiento interno CED\s*\([^)]*\):?\s*",
        "",
        text or "",
        flags=re.I,
    )
    cleaned = re.sub(
        r"-\s*\[[^\]]+\][^.\n]*\.?\s*",
        "",
        cleaned,
        flags=re.I,
    )
    cleaned = re.sub(
        r"(?:^|\n)-\s*\[[^\]]+\][^\n]*",
        "",
        cleaned,
        flags=re.I,
    )
    return " ".join(cleaned.split()).strip()
