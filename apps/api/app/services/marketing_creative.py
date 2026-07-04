"""Detección y brief de creativos publicitarios (genérico — cualquier producto/marca)."""

from __future__ import annotations

import re

from app.services.chat_intents import (
    is_generate_image_intent,
    parse_followup_image_prompt,
    parse_generate_image_prompt,
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
_BENEFIT_LINE = re.compile(
    r"(?:^|\n)\s*(?:[\*\-•]\s*)?"
    r"([A-Za-zÁÉÍÓÚáéíóúÑñ0-9][A-Za-zÁÉÍÓÚáéíóúÑñ0-9\s]{2,35})\s*:\s*"
    r"(.{8,160}?)(?=\n|$|\*|\-|\•|[A-ZÁÉÍÓÚ][a-záéíóú]+:)",
    re.M,
)
_SKIP_BENEFIT_TITLES = frozenset(
    {
        "características",
        "caracteristicas",
        "beneficios",
        "referencia",
        "información",
        "informacion",
        "nota",
        "ejemplo",
    }
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
    bullets: list[str] = []
    for match in _BENEFIT_LINE.finditer(text or ""):
        title = match.group(1).strip()
        desc = re.sub(r"\s+", " ", match.group(2).strip())
        if title.lower() in _SKIP_BENEFIT_TITLES:
            continue
        if len(desc) < 8:
            continue
        bullets.append(f"{title}: {desc[:90]}")
        if len(bullets) >= max_bullets:
            break
    return bullets


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
    subject = _extract_product_subject(f"{raw}\n{context}")
    bullets = _extract_benefit_bullets(context)
    if not bullets:
        bullets = _extract_benefit_bullets(raw)

    bullet_block = ""
    if bullets:
        bullet_block = "Textos cortos en español para el diseño:\n" + "\n".join(
            f"• {line}" for line in bullets
        )

    user_note = raw[:240] if raw else user_text[:240]
    display = build_display_label(
        subject,
        kind="flyer" if re.search(r"\bflyer\b", user_text, re.I) else "creativo",
    )

    if has_reference_image:
        internal = (
            "Usa la imagen adjunta como base: producto/envase protagonista, fondo limpio. "
            "Crea un flyer publicitario cuadrado para redes sociales, estilo profesional de venta. "
            f"Sujeto: {subject}. "
        )
        if bullet_block:
            internal += f"{bullet_block} "
        internal += (
            "Tipografía legible, pocos bloques de texto, composición atractiva. "
            f"Instrucción del cliente: {user_note}"
        )
        style_mode = "edit"
    else:
        internal = (
            "Genera un flyer publicitario cuadrado para redes sociales. "
            f"Sujeto visual: {subject}. "
            "Producto o envase premium en primer plano, estilo profesional de venta. "
        )
        if bullet_block:
            internal += f"{bullet_block} "
        internal += (
            "Sin logos de marcas registradas de terceros; diseño genérico elegante. "
            f"Referencia: {context[:700]}. Pedido: {user_note}"
        )
        style_mode = "inspired"

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
