"""Normalización de claves OpenAI desde variables de entorno."""

from __future__ import annotations

import re

_SK_PATTERN = re.compile(r"sk-(?:proj-)?[A-Za-z0-9_\-]+")


def sanitize_openai_api_key(raw: str) -> str:
    """Quita comillas, saltos de línea y extrae sk-... de pegados mal formados."""
    val = (raw or "").strip().strip('"').strip("'")
    if not val:
        return ""

    if val.startswith("sk-"):
        return val.split()[0].strip('"').strip("'")

    match = _SK_PATTERN.search(val)
    if match:
        return match.group(0)

    for token in val.replace("\n", " ").replace("\t", " ").split():
        cleaned = token.strip('"').strip("'").strip(",")
        if cleaned.startswith("sk-"):
            return cleaned
        m = _SK_PATTERN.search(cleaned)
        if m:
            return m.group(0)

    return val


def openai_api_key_looks_valid(key: str) -> bool:
    k = sanitize_openai_api_key(key)
    return k.startswith("sk-") and 20 <= len(k) <= 220
