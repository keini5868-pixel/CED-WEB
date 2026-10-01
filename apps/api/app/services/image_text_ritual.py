"""Imagen + texto: cerrar el overlay antes de Ideogram (ritmo Jarvis)."""

from __future__ import annotations

import re

from app.services.chat_intents import (
    assistant_offered_image_act,
    is_bare_affirmation,
    is_explicit_image_command,
    is_exploratory_talk,
    is_generate_image_intent,
    is_image_choice_confirmation,
    is_script_narrative_request,
    last_concrete_image_user_prompt,
    last_user_visual_context,
    wants_image_reference_edit,
)
from app.services.copy_quality import (
    build_image_headline,
    extract_quoted_phrases,
    extract_spoken_overlay_labels,
    prompt_requires_precise_text,
)
from app.services.marketing_creative import extract_product_subject

# Pedido cuyo entregable ES el gráfico con copy (no «rompiendo un cartel» en una escena).
_GRAPHIC_DELIVERABLE = re.compile(
    r"(?is)\b(?:gen[eé]r\w*|cr[eé]a\w*|haz(?:me|lo|la)?|dise[nñ]a\w*|"
    r"quiero|necesito|dame)\b.{0,28}\b(?:una?\s+|un\s+|el\s+|la\s+)?"
    r"(?:flyer|banner|cartel|letrero|r[oó]tulo|infograf[ií]a)\b"
)

_QUE_DIGA = re.compile(
    r"(?is)que\s+(?:diga[n]?|ponga[n]?|lea)\s+"
    r"(?:[«\"'“]([^\"'»”\n]{2,80})[»\"'”]|([A-ZÁÉÍÓÚÑ0-9][^.\n?]{1,72}))"
)

_CON_FRASE = re.compile(
    r"(?is)(?:con\s+(?:el\s+texto|la\s+frase|las?\s+palabras?))\s+"
    r"[«\"'“]?([^\"'»”\n.]{2,80})"
)

_ETIQUETAS = re.compile(
    r"(?is)\betiquetas?\s*:?\s+(.+?)(?:\s+en\s+texto\b|$)"
)

_ESCRITOS_BLOCK = re.compile(
    r"(?is)(?:detalles?\s+(?:resumidos\s+)?escritos?)\s+(.{12,400})"
)

_READBACK_LOCK = re.compile(
    r"(?is)va a decir exactamente:\s*[«\"']?([^\"'»\n.¿?]{2,80})"
)

_VAGUE_OVERLAY = re.compile(
    r"(?is)^(un|una|el|la|los|las)\s+(resumen|texto|algo|copy)\b"
)

_PREPOSITION_LEAD = re.compile(
    r"(?is)^(de|del|de la|para|con|en)\s+(.+)$"
)
_CHANNEL_ONLY = re.compile(
    r"(?is)^(para\s+)?(?:instagram|facebook|meta|tiktok|feed|stories?|"
    r"redes(?:\s+sociales)?)$"
)
_OFFER_LEAK = re.compile(r"(?is)\b(?:la\s+genero|dime el texto exacto)\b")

# Titulares cortos de catálogo interno — sin precios ni Tavily.
_FITLINE_HEADLINES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?i)\brestorate\b"), "Restorate — recuperación celular"),
    (re.compile(r"(?i)\bactivize|activise\b"), "Activize — energía del día"),
    (re.compile(r"(?i)\bpower\s*cocktail\b"), "PowerCocktail — vitalidad diaria"),
    (re.compile(r"(?i)\bbasics\b"), "Basics — nutrición diaria"),
    (re.compile(r"(?i)\boptimal[\s-]?set\b"), "Optimal-Set — nutrición integral"),
    (re.compile(r"(?i)\bfitline|fit\s*line|pm\s*international\b"), "FitLine — nutrición celular"),
)

_DELIVERY = "Listo. El texto es el que acordamos."


def _clean_overlay(raw: str) -> str | None:
    t = re.sub(r"\s+", " ", (raw or "").strip()).strip(" .,;:¿?")
    if len(t) < 2 or len(t) > 80:
        return None
    if _VAGUE_OVERLAY.match(t) or _OFFER_LEAK.search(t):
        return None
    return t


def _usable_headline(raw: str) -> str | None:
    t = _clean_overlay(raw)
    if not t:
        return None
    if _CHANNEL_ONLY.match(t):
        return None
    lead = _PREPOSITION_LEAD.match(t)
    if lead:
        t = _clean_overlay(lead.group(2) or "")
        if not t or _CHANNEL_ONLY.match(t):
            return None
    if t.lower() in {"instagram", "facebook", "flyer", "imagen", "banner", "creativo"}:
        return None
    return t


def fitline_overlay_headline(text: str) -> str | None:
    blob = text or ""
    for pat, line in _FITLINE_HEADLINES:
        if pat.search(blob):
            return line
    return None


def _extract_from_text(text: str) -> list[str]:
    t = (text or "").strip()
    if not t or is_script_narrative_request(t):
        return []
    found: list[str] = []

    def _add(raw: str) -> None:
        clean = _clean_overlay(raw)
        if clean and clean not in found:
            found.append(clean)

    for phrase in extract_quoted_phrases(t):
        _add(phrase)
    for match in _QUE_DIGA.finditer(t):
        _add(match.group(1) or match.group(2) or "")
    for match in _CON_FRASE.finditer(t):
        _add(match.group(1) or "")
    for match in _READBACK_LOCK.finditer(t):
        _add(match.group(1) or "")
    for match in _ETIQUETAS.finditer(t):
        blob = (match.group(1) or "").strip()
        for part in re.split(r"\s*,\s*|\s+y\s+", blob):
            _add(part)
    for match in _ESCRITOS_BLOCK.finditer(t):
        first = (match.group(1) or "").split("\n", 1)[0].strip()
        _add(first[:72])
    for label in extract_spoken_overlay_labels(t):
        _add(label)
    return found


def locked_overlay_lines(
    text: str,
    history: list[dict[str, str]] | None = None,
) -> list[str]:
    """Palabras exactas a pintar: comillas, «que diga», etiquetas o el read-back de CED."""
    found = _extract_from_text(text)
    if found:
        return found
    for row in reversed(history or []):
        found = _extract_from_text(str(row.get("content") or ""))
        if found:
            return found
    return []


def overlay_is_locked(
    text: str,
    history: list[dict[str, str]] | None = None,
) -> bool:
    return bool(locked_overlay_lines(text, history))


_EXPLICIT_TEXT_ASK = re.compile(
    r"(?is)\b(?:en\s+texto|con\s+texto|que\s+diga|con\s+el\s+texto|con\s+la\s+frase)\b"
)


def _wants_graphic_copy(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if _GRAPHIC_DELIVERABLE.search(t):
        return True
    if wants_image_reference_edit(t) and prompt_requires_precise_text(t):
        return True
    if _EXPLICIT_TEXT_ASK.search(t) and (
        is_generate_image_intent(t) or is_explicit_image_command(t)
    ):
        return True
    return False


def needs_overlay_readback(
    text: str,
    history: list[dict[str, str]] | None = None,
) -> bool:
    """True: mandaron generar un gráfico con copy, pero las palabras no están cerradas."""
    t = (text or "").strip()
    if not t:
        return False
    if is_bare_affirmation(t) or is_image_choice_confirmation(t):
        return False
    if is_exploratory_talk(t) and not is_explicit_image_command(t):
        return False
    if overlay_is_locked(t, history):
        return False
    if not _wants_graphic_copy(t):
        return False
    return True


def proposed_overlay_line(
    text: str,
    history: list[dict[str, str]] | None = None,
) -> str | None:
    locked = locked_overlay_lines(text, history)
    if locked:
        usable = _usable_headline(locked[0])
        if usable:
            return usable
    blob = " ".join(
        part
        for part in (
            text,
            last_concrete_image_user_prompt(history) or "",
            last_user_visual_context(history) or "",
        )
        if part
    )
    fitline = fitline_overlay_headline(blob)
    if fitline:
        return fitline
    subject = extract_product_subject(blob) or extract_product_subject(text or "")
    headline = build_image_headline(text or blob, subject or "")
    return _usable_headline(headline) or _usable_headline(subject or "")


def build_overlay_readback_reply(
    text: str,
    history: list[dict[str, str]] | None = None,
) -> str:
    line = proposed_overlay_line(text, history)
    if line:
        return f"En la pieza va a decir exactamente: {line}. ¿La genero?"
    return "Dime el texto exacto que va en la pieza. ¿La genero cuando lo tengas?"


def compose_confirmed_overlay_prompt(
    text: str,
    history: list[dict[str, str]] | None = None,
) -> str | None:
    """«sí» tras el read-back → brief previo + overlay cerrado."""
    t = (text or "").strip()
    if not (is_bare_affirmation(t) or is_image_choice_confirmation(t)):
        return None
    if not assistant_offered_image_act(history):
        return None
    locked = locked_overlay_lines("", history)
    prior = (
        last_concrete_image_user_prompt(history)
        or last_user_visual_context(history)
        or "flyer"
    )
    if not locked:
        return prior
    line = _usable_headline(locked[0]) or locked[0]
    if _OFFER_LEAK.search(line):
        return prior
    if line.lower() in prior.lower():
        return prior
    return f'{prior.rstrip(".")} que diga "{line}"'


def delivery_caption_for_image(
    text: str = "",
    history: list[dict[str, str]] | None = None,
) -> str | None:
    if overlay_is_locked(text, history):
        return _DELIVERY
    return None
