"""Detección directa de intents en chat de texto (sin depender del LLM)."""

from __future__ import annotations

import re

_CREATE_VERBS = (
    r"(?:gener(?:a(?:r|me|mos|s|is|n|do)?|ame|áme)|"
    r"cre(?:a(?:r|me|mos|s|is|n|do)?|ame|áme)|"
    r"cr[eé]ame|gener[aá]me|"
    r"haz(?:me|nos|lo|la|es|emos|er|go)?|hacer(?:me|lo)?|"
    r"dise[nñ]a(?:r|me|mos|s|is|n|do)?|"
    r"dibuja(?:r|me|mos|s)?|pinta(?:r|me|mos|s)?|"
    r"dame|hazme)"
)
_IMAGE_NOUN = r"(?:imagen|foto|picture|ilustraci[oó]n|dise[nñ]o|arte|gr[aá]fico|creativo|logo|banner|flyer|portada)"

_IMAGE_PATTERNS = (
    re.compile(rf"\b{_CREATE_VERBS}\s+(?:una?\s+)?{_IMAGE_NOUN}\b", re.I),
    re.compile(rf"\b{_IMAGE_NOUN}\s+(?:de|con|para)\b", re.I),
    re.compile(rf"\bquiero\s+(?:que\s+)?{_CREATE_VERBS}\s+(?:una?\s+)?{_IMAGE_NOUN}\b", re.I),
    re.compile(rf"\bnecesito\s+(?:una?\s+)?{_IMAGE_NOUN}\b", re.I),
    re.compile(rf"\bpuedes\s+{_CREATE_VERBS}\s+(?:una?\s+)?{_IMAGE_NOUN}\b", re.I),
    re.compile(
        rf"\b{_CREATE_VERBS}\b.+\b{_IMAGE_NOUN}\b|\b{_IMAGE_NOUN}\b.+\b{_CREATE_VERBS}\b",
        re.I,
    ),
)

_IMAGE_PROMPT_PATTERNS = (
    re.compile(
        rf"(?:\b(?:me\s+)?(?:puedes\s+)?{_CREATE_VERBS}\s+(?:una?\s+)?{_IMAGE_NOUN}\s+"
        rf"(?:de|con|para|que\s+)?\s*[:.]?\s*(.+))$",
        re.I,
    ),
    re.compile(rf"\b{_IMAGE_NOUN}\s+de\s+(.+)$", re.I),
    re.compile(
        rf"\bquiero\s+(?:que\s+)?{_CREATE_VERBS}\s+(?:una?\s+)?{_IMAGE_NOUN}\s+(?:de|con|para|que\s+)?\s*[:.]?\s*(.+)$",
        re.I,
    ),
    re.compile(
        rf"\bnecesito\s+(?:una?\s+)?{_IMAGE_NOUN}\s+(?:de|con|para|que\s+)?\s*[:.]?\s*(.+)$",
        re.I,
    ),
    re.compile(
        rf"\bpuedes\s+{_CREATE_VERBS}\s+(?:una?\s+)?{_IMAGE_NOUN}\s+(?:de|con|para|que\s+)?\s*[:.]?\s*(.+)$",
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


_FOLLOWUP_IMAGE_CONTEXT = re.compile(
    r"\b(genera(?:r|me|nos|do)?|crea(?:r|me|nos|do)?|imagen|foto|dise[nñ]o|"
    r"creativo|ilustraci[oó]n|face(?:book)?|instagram|publicar|banner|flyer)\b",
    re.I,
)
_FOLLOWUP_SKIP = re.compile(
    r"^(?:ok|gracias|s[ií]|no|vale|perfecto|listo|env[ií]a|publica|dale|hola|buenas)\b",
    re.I,
)


def parse_followup_image_prompt(text: str, history: list[dict[str, str]] | None = None) -> str | None:
    """Detecta pedidos cortos de imagen que continúan un tema visual reciente."""
    t = (text or "").strip()
    if not t or is_generate_image_intent(t) or len(t) > 120 or len(t) < 6:
        return None
    if _FOLLOWUP_SKIP.search(t):
        return None
    recent: list[str] = []
    for row in (history or [])[-8:]:
        content = (row.get("content") or "").strip()
        if content:
            recent.append(content)
    blob = " ".join(recent[-6:]).lower()
    if not _FOLLOWUP_IMAGE_CONTEXT.search(blob):
        return None
    return t


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
