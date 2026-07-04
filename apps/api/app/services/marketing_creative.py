"""Detección y brief de creativos con imagen (genérico — producto, evento, servicio, curso…)."""

from __future__ import annotations

import re

from app.services.chat_intents import (
    is_generate_image_intent,
    parse_followup_image_prompt,
    parse_generate_image_prompt,
)
from app.services.copy_quality import (
    build_image_headline,
    collect_image_overlay_lines,
    extract_structured_lines,
    extract_structured_lines_from_history,
    format_creative_image_copy,
    normalize_spanish,
)
from app.services.gemini_images import strip_image_generation_instruction

CREATIVO_PROMPT_MARKER = "[[CREATIVO]]"

_CREATIVE_TAIL_NOISE = re.compile(
    r"\s*(?:"
    r"y\s+que\s+.*(?:referencia|fondo|imegen|imagen|imajen)"
    r"|(?:expli|espli)\w*.*(?:referencia|fondo|imegen|imagen)"
    r"|(?:usa|utiliza)\w*\s+(?:esta|ese|la|el|mi)?\s*(?:imagen|foto|imegen|fotograf[ií]a)?\s*"
    r"(?:de\s+)?(?:referencia\s+)?(?:en\s+el\s+)?(?:fondo|detr[aá]s|base)(?:\s+(?:del|de\s+el)\s+\w+)?"
    r"|(?:usa|pon)\s+.*(?:referencia|fondo|detr[aá]s|imagen\s+adjunta)"
    r").*$",
    re.I | re.S,
)
_META_INSTRUCTION_FRAGMENT = re.compile(
    r"^(?:"
    r"(?:usa|utiliza)\s+(?:esta|ese|la|el|mi)?\s*(?:imagen|foto|imegen)?\s*"
    r"|(?:referencia|fondo|detr[aá]s)\b"
    r")",
    re.I,
)
_CREATIVE_HEAD_NOISE = re.compile(
    r"^(?:"
    r"estas?\s+caracter[ií]sticas\s*"
    r"|con\s+estas?\s+caracter[ií]sticas\s*"
    r")",
    re.I,
)

_CREATIVE_TYPO_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"vbeneficios?", re.I), "beneficios"),
    (re.compile(r"veneficios?", re.I), "beneficios"),
    (re.compile(r"imegenes?", re.I), "imagen"),
    (re.compile(r"imajenes?", re.I), "imagen"),
    (re.compile(r"especificaciones?", re.I), "especificaciones"),
    (re.compile(r"caracteristicas?", re.I), "características"),
)

_MARKETING_CREATIVE = re.compile(
    r"\b("
    r"flyer|creativo|banner|publicidad|anuncio|post\s+de\s+venta|"
    r"especificaciones|beneficios|veneficios|ventajas|puntos?\s+clave|caracter[ií]sticas|"
    r"agenda|horarios?|m[oó]dulos?|programa|invitaci[oó]n|promoci[oó]n|"
    r"evento|curso|taller|servicio|"
    r"vender|vendiendo|dise[nñ]o\s+(?:de\s+)?venta|"
    r"pon\s+(?:de\s+)?fondo|usa\s+(?:esta|esta)\s+imagen|"
    r"textos?\s+(?:escritos|encima|sobre)|"
    r"presentaci[oó]n\s+(?:de\s+)?(?:producto|servicio|evento|marca)"
    r")\b",
    re.I,
)
_STRUCTURED_CONTENT = re.compile(
    r"\b("
    r"beneficios?|veneficios?|ventajas?|puntos?\s+clave|caracter[ií]sticas|"
    r"especificaciones|agenda|horarios?|m[oó]dulos?|temas?|programa|"
    r"servicios?|promoci[oó]n|invitaci[oó]n|incluye"
    r")\b",
    re.I,
)
_VISUAL_REFERENCE = re.compile(
    r"\b("
    r"referencia|fondo|detr[aá]s|base|"
    r"imagen|foto|flyer|creativo|"
    r"expli[qc]\w*|muestra|present|adjunt"
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


def normalize_creative_request_text(text: str) -> str:
    """Normaliza typos de voz/dictado antes de detectar creativos."""
    t = (text or "").strip()
    for pattern, repl in _CREATIVE_TYPO_REPLACEMENTS:
        t = pattern.sub(repl, t)
    return t


def strip_creative_user_noise(text: str) -> str:
    """Quita instrucciones meta («genera imagen», «usa referencia en fondo») del contenido."""
    t = strip_image_generation_instruction(text or "")
    t = normalize_creative_request_text(t)
    t = _CREATIVE_TAIL_NOISE.sub("", t).strip()
    t = _CREATIVE_HEAD_NOISE.sub("", t).strip()
    t = re.sub(r"^\*+\s*", "", t)
    return t.strip()


def _is_meta_instruction_fragment(text: str) -> bool:
    """Fragmento tipo «referencia en el fondo» sin contenido del tema."""
    t = (text or "").strip()
    if not t or len(t) > 100:
        return False
    if extract_structured_lines(t):
        return False
    if _META_INSTRUCTION_FRAGMENT.search(t):
        return True
    if re.fullmatch(
        r"(?:referencia|fondo|imagen|imegen|detr[aá]s)(?:\s+\w+){0,10}",
        t,
        re.I,
    ):
        return True
    return False


def _merge_creative_raw(primary: str, alternate: str | None) -> str:
    """Conserva el texto con más contenido útil; evita perder viñetas por un tail meta."""
    base = strip_creative_user_noise(primary)
    if not alternate:
        return base
    alt = strip_creative_user_noise(alternate)
    if not alt or alt == base:
        return base
    if _is_meta_instruction_fragment(alt) and extract_structured_lines(base):
        return base
    base_lines = extract_structured_lines(base)
    alt_lines = extract_structured_lines(alt)
    if base_lines and not alt_lines:
        return base
    if alt_lines and not base_lines:
        return alt
    if len(alt_lines) > len(base_lines):
        return alt
    if len(alt) > len(base) and not _is_meta_instruction_fragment(alt):
        return alt
    return base


def is_marketing_creative_intent(text: str) -> bool:
    t = normalize_creative_request_text(text)
    if not t:
        return False
    if _MARKETING_CREATIVE.search(t):
        return True
    if is_generate_image_intent(t) and _STRUCTURED_CONTENT.search(t):
        return True
    return False


def should_build_creative_brief(
    text: str,
    history: list[dict[str, str]] | None = None,
    *,
    has_reference_image: bool = False,
) -> bool:
    """True si conviene reescribir el pedido como brief [[CREATIVO]] (cualquier tema)."""
    raw = (text or "").strip()
    if not raw:
        return False
    clean = strip_creative_user_noise(raw)
    blob = f"{clean}\n{_history_blob(history)}\n{raw}"
    overlay = (
        extract_structured_lines(blob)
        or extract_structured_lines_from_history(history)
    )
    if is_marketing_creative_intent(raw):
        return True
    if len(overlay) >= 2:
        return True
    if has_reference_image and overlay and _VISUAL_REFERENCE.search(normalize_creative_request_text(raw)):
        return True
    if has_reference_image and is_attachment_creative_request(raw, history):
        return True
    if overlay and is_image_creation_request(raw, history):
        return True
    return False


def is_attachment_creative_request(
    text: str,
    history: list[dict[str, str]] | None = None,
) -> bool:
    """Detecta pedido de creativo al adjuntar imagen (incluye typos y beneficios en el mensaje)."""
    raw = (text or "").strip()
    if not raw:
        return False
    t = normalize_creative_request_text(raw)
    if is_image_creation_request(t, history):
        return True

    overlay_lines = (
        extract_structured_lines(raw)
        or extract_structured_lines(t)
        or extract_structured_lines_from_history(history)
    )
    visual_ref = _VISUAL_REFERENCE.search(t)
    if overlay_lines and visual_ref:
        return True
    if overlay_lines and _STRUCTURED_CONTENT.search(t):
        return True
    if overlay_lines and is_generate_image_intent(t):
        return True
    if _STRUCTURED_CONTENT.search(t) and visual_ref:
        return True
    return False


def is_image_creation_request(text: str, history: list[dict[str, str]] | None = None) -> bool:
    """True si el usuario pide generar/editar un creativo, no publicar."""
    t = normalize_creative_request_text(text)
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
    normalized = normalize_creative_request_text(text or "")
    if _MARKETING_CREATIVE.search(normalized) and not _explicit_publish_only(text):
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


_SKIP_SUBJECTS = frozenset(
    {
        "producto",
        "el producto",
        "tema",
        "el tema",
        "en el fondo",
        "referencia",
        "imagen",
        "creativo",
        "flyer",
        "evento",
        "servicio",
    }
)


def _subject_is_usable(subject: str) -> bool:
    clean = re.sub(r"\s+", " ", (subject or "").strip()).lower()
    if len(clean) < 3 or clean in _SKIP_SUBJECTS:
        return False
    if re.fullmatch(r"(fondo|referencia|imagen|producto|tema|evento|servicio)(?:\s+\w+){0,2}", clean):
        return False
    if re.search(r"\b(referencia|fondo|detr[aá]s|imegen|adjunt|instrucci[oó]n)\b", clean):
        return False
    return True


def _extract_creative_subject(context: str) -> str:
    blob = (context or "").strip()
    if not blob:
        return "tema"
    for pattern in (
        r'["«“]([^"»”]{3,60})["»”]',
        r"\b([A-Za-zÁÉÍÓÚáéíóúÑñ0-9][\w\s\-]{2,45})\s+es\s+(?:un|una)\b",
        r"\b(?:producto|servicio|evento|curso|taller|marca|promoci[oó]n|invitaci[oó]n|flyer)\s+"
        r"([^\n,.:;]{3,60})",
        r"\b([A-Za-zÁÉÍÓÚáéíóúÑñ][\w\s\-]{2,30})\s+de\s+([A-Za-zÁÉÍÓÚáéíóúÑñ][\w\s\-]{2,30})\b",
        r"\bproducto\s+([^\n,.:;]{3,60})",
    ):
        match = re.search(pattern, blob, re.I)
        if not match:
            continue
        if match.lastindex and match.lastindex >= 2 and match.group(2):
            subject = f"{match.group(1).strip()} de {match.group(2).strip()}"
        else:
            subject = (match.group(1) if match.lastindex else match.group(0)).strip()
        subject = re.sub(r"\s+", " ", subject)
        if _subject_is_usable(subject):
            return subject[:80]
    return "tema"


def _extract_product_subject(context: str) -> str:
    return _extract_creative_subject(context)


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
    clean = re.sub(r"\s+", " ", (subject or "tema").strip())[:50]
    if kind == "flyer":
        return f"Flyer — {clean}"
    return f"Creativo — {clean}"


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
    raw = strip_creative_user_noise(user_text)
    parsed = parse_generate_image_prompt(user_text) or parse_followup_image_prompt(user_text, history)
    raw = _merge_creative_raw(raw, parsed)

    context = _history_blob(history)
    subject = normalize_spanish(_extract_creative_subject(f"{context}\n{raw}\n{user_text}"))
    overlay_lines = collect_image_overlay_lines(f"{raw}\n{context}", context)
    if not overlay_lines:
        overlay_lines = _extract_benefit_bullets_from_history(history)
    if not overlay_lines:
        overlay_lines = extract_structured_lines(context)

    headline = build_image_headline(context, subject)
    if not headline or headline.lower().startswith(subject.lower()[:8]):
        headline = subject if _subject_is_usable(subject) else headline
    verbatim_block = format_creative_image_copy(overlay_lines, headline=headline or subject)

    display = build_display_label(
        subject,
        kind="flyer" if re.search(r"\bflyer\b", user_text, re.I) else "creativo",
    )

    if has_reference_image:
        internal = (
            f"{CREATIVO_PROMPT_MARKER} "
            "Creativo cuadrado 1:1 para redes sociales. "
            "Usa la foto adjunta: el elemento principal del tema debe verse nítido (centro o fondo). "
            "Diseño limpio, fondo suave desenfocado, tipografía sans-serif grande. "
            "Máximo 4 textos cortos en la imagen. "
            f"Tema: {subject}. "
        )
        if verbatim_block:
            internal += f"{verbatim_block} "
        internal += (
            "Ortografía española impecable. "
            "No escribas párrafos largos ni texto en inglés inventado."
        )
        style_mode = "edit"
    else:
        internal = (
            f"{CREATIVO_PROMPT_MARKER} "
            "Genera un creativo cuadrado para redes sociales. "
            f"Tema: {subject}. "
        )
        if verbatim_block:
            internal += f"{verbatim_block} "
        internal += (
            "Estilo premium, fondo limpio, máximo 4 textos cortos. "
            "Ortografía española impecable."
        )
        style_mode = "inspired"

    return internal[:3800], display, style_mode


def resolve_image_creation_from_attachment(
    user_text: str,
    history: list[dict[str, str]] | None = None,
) -> dict[str, str] | None:
    """Si hay imagen adjunta + pedido de creativo, devuelve brief y metadatos."""
    if not is_attachment_creative_request(user_text, history):
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
