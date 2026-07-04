"""Detección y brief de creativos publicitarios (genérico — cualquier producto/marca)."""

from __future__ import annotations

import re

from app.services.chat_intents import (
    is_generate_image_intent,
    parse_followup_image_prompt,
    parse_generate_image_prompt,
)
from app.services.copy_quality import (
    augment_image_prompt,
    build_image_headline,
    collect_image_overlay_lines,
    extract_structured_lines,
    extract_structured_lines_from_history,
    format_verbatim_image_copy,
    normalize_spanish,
)
from app.services.gemini_images import strip_image_generation_instruction

_MARKETING_CREATIVE = re.compile(
    r"\b("
    r"flyer|creativo|banner|publicidad|anuncio|post\s+de\s+venta|"
    r"especificaciones|beneficios|veneficios|caracter[ií]sticas|"
    r"vender|vendiendo|dise[nñ]o\s+(?:de\s+)?venta|"
    r"pon\s+(?:de\s+)?fondo|usa\s+(?:esta|esta)\s+imagen|"
    r"textos?\s+(?:escritos|encima|sobre)|"
    r"presentaci[oó]n\s+de\s+producto"
    r")\b",
    re.I,
)
_PUBLISH_ONLY = re.compile(
    r"\b(publica(?:r|me|lo|la)?|sube(?:r|me|lo)?|postea(?:r|me|lo)?|"
    r"comparte(?:r|me|lo)?|env[ií]a(?:r|me|lo|la)?)\b",
    re.I,
)
_PRODUCT_SUBJECT = re.compile(
    r"\b(?:"
    r"producto\s+([^\n,.:;]{3,60})|"
    r"([A-Za-zÁÉÍÓÚáéíóúÑñ0-9][\w\s\-]{2,40})\s+de\s+([A-Za-zÁÉÍÓÚáéíóúÑñ][\w\s\-]{2,40})|"
    r"([A-Za-zÁÉÍÓÚáéíóúÑñ][\w\s\-]{2,40})\s+es\s+(?:un|una)\s+"
    r")",
    re.I,
)


def is_marketing_creative_intent(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if _MARKETING_CREATIVE.search(t):
        return True
    if is_generate_image_intent(t) and re.search(
        r"\b(beneficios|veneficios|especificaciones|caracter[ií]sticas|producto)\b",
        t,
        re.I,
    ):
        return True
    return False


def is_image_creation_request(text: str, history: list[dict[str, str]] | None = None) -> bool:
    """True si el usuario pide generar/editar un creativo, no publicar."""
    t = (text or "").strip()
    if not t:
        return False
    if is_generate_image_intent(t):
        return True
    if is_marketing_creative_intent(t):
        return True
    if parse_followup_image_prompt(t, history):
        return True
    if re.search(r"\b(genera|crea|haz|dise[nñ]a)\b.+\b(imagen|foto|flyer|creativo)\b", t, re.I):
        return True
    return False


def blocks_publish_intent(text: str, history: list[dict[str, str]] | None = None) -> bool:
    """Evita confundir «flyer/creativo» con flujo de publicación Meta."""
    if is_image_creation_request(text, history):
        return True
    if _MARKETING_CREATIVE.search(text or "") and not _explicit_publish_only(text):
        return True
    return False


def _explicit_publish_only(text: str) -> bool:
    t = (text or "").strip()
    if not _PUBLISH_ONLY.search(t):
        return False
    if is_marketing_creative_intent(t):
        return False
    return True


def _history_blob(history: list[dict[str, str]] | None, *, limit: int = 8) -> str:
    chunks: list[str] = []
    for row in (history or [])[-limit:]:
        content = (row.get("content") or "").strip()
        if content:
            chunks.append(content)
    return "\n".join(chunks)


def _extract_product_subject(context: str) -> str:
    blob = (context or "").strip()
    if not blob:
        return "producto"
    for pattern in (
        r"\bproducto\s+([^\n,.:;]{3,60})",
        r"\b([A-Za-zÁÉÍÓÚáéíóúÑñ][\w\s\-]{2,30})\s+de\s+([A-Za-zÁÉÍÓÚáéíóúÑñ][\w\s\-]{2,30})\b",
        r"\b([A-Za-zÁÉÍÓÚáéíóúÑñ][\w\s\-]{3,40})\s+es\s+(?:un|una)\b",
    ):
        match = re.search(pattern, blob, re.I)
        if not match:
            continue
        if match.lastindex and match.lastindex >= 2:
            subject = f"{match.group(1).strip()} de {match.group(2).strip()}"
        else:
            subject = (match.group(1) if match.lastindex else match.group(0)).strip()
        subject = re.sub(r"\s+", " ", subject)
        if len(subject) >= 3 and subject.lower() not in {"producto", "el producto"}:
            return subject[:80]
    return "producto"


def _extract_benefit_bullets(text: str, *, max_bullets: int = 4) -> list[str]:
    return extract_structured_lines(text, max_lines=max_bullets)


def _extract_benefit_bullets_from_history(
    history: list[dict[str, str]] | None,
    *,
    max_bullets: int = 4,
) -> list[str]:
    return extract_structured_lines_from_history(history, max_lines=max_bullets)


def extract_product_subject(context: str) -> str:
    return _extract_product_subject(context)


def build_display_label(subject: str, *, kind: str = "creativo") -> str:
    clean = re.sub(r"\s+", " ", (subject or "producto").strip())[:50]
    if kind == "flyer":
        return f"Flyer publicitario — {clean}"
    return f"Creativo publicitario — {clean}"


def build_marketing_creative_brief(
    user_text: str,
    history: list[dict[str, str]] | None = None,
    *,
    has_reference_image: bool = False,
) -> tuple[str, str, str]:
    """
    Devuelve (prompt_interno, etiqueta_visible, style_mode).
    style_mode: edit | inspired | variation
    """
    raw = strip_image_generation_instruction(user_text)
    parsed = parse_generate_image_prompt(user_text) or parse_followup_image_prompt(user_text, history)
    if parsed:
        raw = strip_image_generation_instruction(parsed)

    context = _history_blob(history)
    subject = normalize_spanish(_extract_product_subject(f"{raw}\n{context}"))
    overlay_lines = collect_image_overlay_lines(f"{raw}\n{user_text}", context)
    if not overlay_lines:
        overlay_lines = _extract_benefit_bullets_from_history(history)
    if not overlay_lines:
        overlay_lines = extract_structured_lines(context)

    headline = build_image_headline(context, subject)
    verbatim_block = format_verbatim_image_copy(overlay_lines, headline=headline or None)

    user_note = normalize_spanish(raw[:240] if raw else user_text[:240])
    display = build_display_label(
        subject,
        kind="flyer" if re.search(r"\bflyer\b", user_text, re.I) else "creativo",
    )

    if has_reference_image:
        internal = (
            "Usa la imagen adjunta como base visual principal. "
            "Crea un creativo cuadrado para redes sociales, estilo profesional. "
            f"Tema: {subject}. "
        )
        if verbatim_block:
            internal += f"{verbatim_block} "
        internal += f"Instrucción del cliente: {user_note}"
        style_mode = "edit"
    else:
        internal = (
            "Genera un creativo cuadrado para redes sociales. "
            f"Tema visual: {subject}. "
        )
        if verbatim_block:
            internal += f"{verbatim_block} "
        internal += f"Referencia: {context[:500]}. Pedido: {user_note}"
        style_mode = "inspired"

    internal = augment_image_prompt(internal, context)
    return internal[:4000], display, style_mode


def resolve_image_creation_from_attachment(
    user_text: str,
    history: list[dict[str, str]] | None = None,
) -> dict[str, str] | None:
    """Si hay imagen adjunta + pedido de creativo, devuelve brief y metadatos."""
    if not is_image_creation_request(user_text, history):
        return None
    internal, display, style_mode = build_marketing_creative_brief(
        user_text,
        history,
        has_reference_image=True,
    )
    return {
        "internal_prompt": internal,
        "display_label": display,
        "style_mode": style_mode,
        "reply": f"Listo, señor. Aquí está su {display.lower()}.",
    }


def resolve_image_creation_from_text(
    user_text: str,
    history: list[dict[str, str]] | None = None,
) -> dict[str, str] | None:
    """Pedido de creativo sin adjunto (solo texto + historial)."""
    if not is_image_creation_request(user_text, history):
        return None
    if is_marketing_creative_intent(user_text) or parse_followup_image_prompt(user_text, history):
        internal, display, style_mode = build_marketing_creative_brief(
            user_text,
            history,
            has_reference_image=False,
        )
        return {
            "internal_prompt": internal,
            "display_label": display,
            "style_mode": style_mode,
            "reply": f"Listo, señor. Aquí está su {display.lower()}.",
        }
    return None
