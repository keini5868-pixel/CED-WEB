"""Extrae solo el contenido publicable — sin instrucciones del usuario."""

from __future__ import annotations

import re

_INSTRUCTION_PREFIX = re.compile(
    r"^(?:"
    r"(?:que\s+)?(?:diga|dice)\s+|"
    r"(?:con\s+el\s+)?texto\s*:?\s*|"
    r"(?:hazme\s+)?(?:una\s+)?publicaci[oó]n\s+que\s+diga\s+|"
    r"(?:un\s+)?post\s+que\s+diga\s+|"
    r"esto\s*:?\s*"
    r")",
    re.IGNORECASE,
)

_QUOTED = re.compile(r'^["\'](.+)["\']$')


def strip_publish_instruction(raw: str) -> str:
    """Quita prefijos como 'que diga', 'hazme una publicación que diga'."""
    text = (raw or "").strip(" .,:;-")
    if not text:
        return ""
    for _ in range(4):
        m = _INSTRUCTION_PREFIX.match(text)
        if not m:
            break
        text = text[m.end() :].strip(" .,:;-")
    q = _QUOTED.match(text)
    if q:
        text = q.group(1).strip(" .,:;-")
    return text


def extract_publish_body(user_text: str, platform: str = "facebook") -> str:
    """Extrae cuerpo publicable desde frases naturales de voz."""
    last = (user_text or "").strip()
    if not last:
        return ""
    patterns = (
        r"\b(?:hazme\s+)?(?:una\s+)?publicaci[oó]n\s+que\s+diga\s+(.+)$",
        rf"\bpublica(?:r|me|lo|que|ar)?\s+(?:en\s+)?(?:{platform}|ig|fb|instagram|facebook)\s*[:.]?\s*"
        r"(?:que\s+)?(?:diga|dice|con\s+el\s+texto|esto)?\s*[:.]?\s*(.+)$",
        r"\b(?:sube|postea)(?:r|me|lo)?\s+(?:en\s+)?(?:instagram|ig|facebook|fb)\s*[:.]?\s*"
        r"(?:que\s+)?(?:diga|dice|con\s+el\s+texto|esto)?\s*[:.]?\s*(.+)$",
        r"\b(?:publica|postea)\s*[:.]?\s*(.+)$",
    )
    for pat in patterns:
        m = re.search(pat, last, re.I)
        if m and m.group(1):
            body = strip_publish_instruction(m.group(1))
            if body:
                return body
    quoted = re.search(r'["\'](.+?)["\']', last)
    if quoted and quoted.group(1).strip():
        return strip_publish_instruction(quoted.group(1))
    return strip_publish_instruction(last)
