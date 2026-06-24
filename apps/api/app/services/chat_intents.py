"""Detección directa de intents en chat de texto (sin depender del LLM)."""

from __future__ import annotations

import re

_CREATE_VERBS = r"(?:crea(?:r|me|s|do)?|genera(?:r|me|s|do)?|haz(?:me|lo|la)?|dise[nñ]a(?:r|me|s|do)?|hacer|generar|crear|diseñar)"

_IMAGE_PATTERNS = (
    re.compile(
        r"\b(genera|generar|crea|cresa|crear|dise[nñ]a|haz(me)?|dame|necesito)\s+(?:una?\s+)?imagen\b",
        re.I,
    ),
    re.compile(
        r"\b(genera|crea|haz|dame|dise[nñ]a)\s+(?:un|una)\s+(?:logo|banner|flyer|portada|arte|gr[aá]fico|creativo|foto)\b",
        re.I,
    ),
    re.compile(r"\b(imagen|foto)\s+de\b", re.I),
    re.compile(r"\bcrea\s+una\s+foto\b", re.I),
    re.compile(
        rf"\bquiero\s+(?:que\s+)?{_CREATE_VERBS}\s+(?:una?\s+)?imagen\b",
        re.I,
    ),
    re.compile(r"\bnecesito\s+(?:una?\s+)?imagen\b", re.I),
    re.compile(
        rf"\bpuedes\s+{_CREATE_VERBS}\s+(?:una?\s+)?imagen\b",
        re.I,
    ),
    re.compile(
        rf"\b(?:crea(?:me)?|dise[nñ]a(?:me)?|haz(?:me)?)\s+(?:una?\s+)?imagen\b",
        re.I,
    ),
    re.compile(
        rf"\bimagen\b.+\b{_CREATE_VERBS}\b|\b{_CREATE_VERBS}\b.+\bimagen\b",
        re.I,
    ),
)

_IMAGE_PROMPT_PATTERNS = (
    re.compile(
        r"\b(?:genera|generar|crea|cresa|crear|dise[nñ]a|haz|dame)\s+(?:una?\s+)?imagen\s+(?:de|con|que\s+diga|que\s+sea)?\s*[:.]?\s*(.+)$",
        re.I,
    ),
    re.compile(
        r"\b(?:genera|crea|haz|dame)\s+(?:un|una)\s+(?:logo|banner|flyer|portada|gr[aá]fico|creativo|foto)\s+(?:de|con|para)?\s*[:.]?\s*(.+)$",
        re.I,
    ),
    re.compile(r"\bimagen\s+de\s+(.+)$", re.I),
    re.compile(
        rf"\bquiero\s+(?:que\s+)?{_CREATE_VERBS}\s+(?:una?\s+)?imagen\s+(?:de|con|que\s+)?\s*[:.]?\s*(.+)$",
        re.I,
    ),
    re.compile(
        rf"\bnecesito\s+(?:una?\s+)?imagen\s+(?:de|con|para|que\s+)?\s*[:.]?\s*(.+)$",
        re.I,
    ),
    re.compile(
        rf"\bpuedes\s+{_CREATE_VERBS}\s+(?:una?\s+)?imagen\s+(?:de|con|para|que\s+)?\s*[:.]?\s*(.+)$",
        re.I,
    ),
    re.compile(
        rf"\b(?:crea(?:me)?|dise[nñ]a(?:me)?|haz(?:me)?)\s+(?:una?\s+)?imagen\s+(?:de|con|para|que\s+)?\s*[:.]?\s*(.+)$",
        re.I,
    ),
)

_PDF_PATTERNS = (
    re.compile(
        r"\b(genera|generar|crea|crear|exporta|exportar|convierte|convertir|guarda|haz(me)?)\s+(?:un(?:a)?\s+)?pdf\b",
        re.I,
    ),
    re.compile(r"\bpdf\s+(?:de|con|sobre|que\s+diga)\b", re.I),
)


def is_generate_image_intent(text: str) -> bool:
    t = text.strip()
    if len(t) < 8:
        return False
    return any(p.search(t) for p in _IMAGE_PATTERNS)


def parse_generate_image_prompt(text: str) -> str | None:
    t = text.strip()
    if not is_generate_image_intent(t):
        return None
    for pattern in _IMAGE_PROMPT_PATTERNS:
        match = pattern.search(t)
        body = (match.group(1) if match else "") or ""
        body = body.strip().strip("\"'")
        if len(body) >= 3:
            return body
    if len(t) >= 12:
        return t
    return None


def is_pdf_intent(text: str) -> bool:
    t = text.strip()
    if len(t) < 8:
        return False
    return any(p.search(t) for p in _PDF_PATTERNS)


def parse_pdf_request(text: str) -> tuple[str, str] | None:
    t = text.strip()
    if not is_pdf_intent(t):
        return None

    title_match = re.search(
        r"(?:t[ií]tulo|titulo)\s*[:.]?\s*[\"']?([^\"'\n.]+?)[\"']?(?:\s+(?:contenido|sobre|de|con)\b|$)",
        t,
        re.I,
    )
    content_match = re.search(
        r"(?:contenido|sobre|de|con|que\s+diga|que\s+incluya)\s*[:.]?\s*(.+)$",
        t,
        re.I | re.S,
    )

    title = (title_match.group(1).strip() if title_match else "") or "Documento CED"
    content = (content_match.group(1).strip() if content_match else "") or ""

    dice_match = re.search(r"que\s+dice\s+(.+)$", t, re.I)
    if dice_match:
        content = dice_match.group(1).strip().strip("\"'")
        if not title_match:
            title = "Documento CED"

    if not content:
        content = re.sub(
            r"^(?:genera|generar|crea|crear|exporta|exportar|convierte|convertir|guarda|haz(me)?)\s+(?:un(?:a)?\s+)?pdf\s*(?:de|con|sobre|que\s+diga)?\s*",
            "",
            t,
            flags=re.I,
        ).strip()

    if not content or len(content) < 1:
        content = title if title != "Documento CED" else "Hola"

    return title[:200], content[:12000]
