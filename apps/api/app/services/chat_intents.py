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
    r"dame|hazme|"
    r"generate|create|make|draw)"
)
_IMAGE_NOUN = (
    r"(?:imagen|foto|picture|illustration|ilustraci[oó]n|dise[nñ]o|arte|artwork|"
    r"gr[aá]fico|creativo|logo|banner|flyer|portada|image|photo|drawing)"
)

_IMAGE_PATTERNS = (
    re.compile(rf"\b{_CREATE_VERBS}\s+(?:an?\s+)?{_IMAGE_NOUN}\b", re.I),
    re.compile(rf"\b{_CREATE_VERBS}\s+(?:me\s+)?(?:an?\s+)?{_IMAGE_NOUN}\b", re.I),
    re.compile(rf"\b{_IMAGE_NOUN}\s+(?:de|con|para|of|with|showing)\b", re.I),
    re.compile(rf"\bquiero\s+(?:que\s+)?{_CREATE_VERBS}\s+(?:una?\s+)?{_IMAGE_NOUN}\b", re.I),
    re.compile(rf"\bnecesito\s+(?:una?\s+)?{_IMAGE_NOUN}\b", re.I),
    re.compile(rf"\bpuedes\s+{_CREATE_VERBS}\s+(?:una?\s+)?{_IMAGE_NOUN}\b", re.I),
    re.compile(rf"\bcan\s+you\s+{_CREATE_VERBS}\s+(?:an?\s+)?{_IMAGE_NOUN}\b", re.I),
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
    re.compile(r"\bpdf\b", re.I),
    re.compile(
        r"\b(genera|generar|gener[aá]me|crea|crear|cr[eé]ame|exporta|exportar|convierte|convertir|"
        r"guarda|guárdame|haz(me)?|dame|pon|pásalo|pasalo)\s+"
        r"(?:.{0,48}?\s+)?(?:en\s+)?(?:un(?:a)?\s+)?pdf\b",
        re.I,
    ),
    re.compile(
        r"\b(?:esto|lo|el\s+plan|la\s+estrategia|ese\s+plan)\s+(?:en\s+)?(?:un(?:a)?\s+)?pdf\b",
        re.I,
    ),
    re.compile(r"\bpdf\s+(?:de|con|sobre|que\s+diga)\b", re.I),
    re.compile(r"\b(?:en|como)\s+(?:un(?:a)?\s+)?pdf\b", re.I),
)

_PDF_THIS_REF = re.compile(
    r"\b("
    r"esto|lo|la\s+informaci[oó]n|esa\s+informaci[oó]n|con\s+eso|"
    r"lo\s+anterior|el\s+plan|la\s+estrategia|ese\s+plan|el\s+documento|"
    r"aqu[ií]\s+(?:presentado|mostrado)"
    r")\b",
    re.I,
)

_PRIOR_REFERENCE = re.compile(
    r"\b("
    r"igual\s+a\s+(?:la\s+)?(?:que\s+)?(?:te\s+)?(?:pas[eé]|sub[ií]|mand[eé]|envi[eé])"
    r"|(?:la|el)\s+(?:misma|mismo)\s+(?:imagen|foto|flyer|creativo|dise[nñ]o|referencia)"
    r"|(?:mism[oa]s?\s+)?(?:precios?|nombre|dise[nñ]o|estilo|textos?)"
    r"|(?:imagen|foto|flyer|creativo)\s+(?:de\s+)?referencia"
    r"|(?:que|la\s+que)\s+(?:te\s+)?(?:pas[eé]|sub[ií]|mand[eé]|envi[eé]|compart[ií])"
    r"|(?:usa|utiliza)\w*\s+(?:esa|esta|la)\s+(?:imagen|foto|referencia)"
    r"|basad[oa]\s+en\s+(?:la\s+)?(?:imagen|foto|referencia)"
    r")\b",
    re.I,
)


def user_requests_prior_reference(text: str) -> bool:
    return bool(_PRIOR_REFERENCE.search((text or "").strip()))


def mentions_pdf(text: str) -> bool:
    return bool(re.search(r"\bpdf\b", (text or "").strip(), re.I))


def is_generate_image_intent(text: str) -> bool:
    t = text.strip()
    if len(t) < 8:
        return False
    if mentions_pdf(t):
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
    r"creativo|ilustraci[oó]n|face(?:book)?|instagram|publicar|banner|flyer|"
    r"referencia|precio|dise[nñ]o|igual|mismo|otra\s+vez|de\s+nuevo)\b",
    re.I,
)
_FOLLOWUP_SKIP = re.compile(
    r"^(?:ok|gracias|s[ií]|no|vale|perfecto|listo|env[ií]a|publica|dale|hola|buenas)\b",
    re.I,
)
_IMAGE_THREAD_USER = re.compile(
    r"\b(?:genera(?:r|me|nos|do)?|crea(?:r|me|nos|do)?|haz(?:me|nos|lo|la)?|dise[nñ]a(?:r|me|mos|s|is|n|do)?)"
    r"\s+(?:una?\s+)?(?:imagen|foto|creativo|flyer|logo|banner|portada|dise[nñ]o)\b",
    re.I,
)
_IMAGE_THREAD_ASSISTANT = re.compile(
    r"(?:Descargar imagen|Creativo\s+[—\-]|imagen generada|"
    r"aqu[ií]\s+est[aá]\s+(?:tu|su)\s+(?:imagen|creativo)|"
    r"\*\*Qu[eé]\s+es\*\*|Detalle visible|Observaciones\s+[—\-])",
    re.I,
)
_CASUAL_CHAT_BLOCK = re.compile(
    r"\b("
    r"cambiando\s+(?:de\s+|el\s+)?tema|otro\s+tema|hablemos\s+de\s+otra|"
    r"dolor\s+de\s+cabeza|mal\s+de\s+cabeza|me\s+duele\s+la\s+cabeza|"
    r"solo\s+quiero\s+charlar|charlar\s+un\s+rato|conversar|platique|platicar|"
    r"estoy\s+(?:mal|enferm|cansad|triste)|me\s+siento|"
    r"por\s+cierto|a\s+prop[oó]sito|"
    r"olvida(?:lo|mos)?|dejemos\s+(?:eso|lo)|"
    r"no\s+(?:sobre|de)\s+(?:eso|marketing|estrategia)"
    r")\b",
    re.I,
)


def is_casual_chat_interrupt(text: str) -> bool:
    """Charla personal o cambio de tema — no enrutar a creativos ni herramientas."""
    t = (text or "").strip()
    if not t:
        return False
    if _CASUAL_CHAT_BLOCK.search(t):
        return True
    from app.services.cognitive_intents import is_personal_vent_intent, is_topic_change

    return is_personal_vent_intent(t) or is_topic_change(t)


def history_has_active_image_thread(history: list[dict[str, str]] | None) -> bool:
    """True solo si hubo un pedido o entrega real de imagen/creativo en el hilo reciente."""
    for row in (history or [])[-8:]:
        content = (row.get("content") or "").strip()
        if not content:
            continue
        role = str(row.get("role") or "").lower()
        if role == "user" and _IMAGE_THREAD_USER.search(content):
            return True
        if role in ("assistant", "model") and _IMAGE_THREAD_ASSISTANT.search(content):
            return True
    return False


def parse_followup_image_prompt(text: str, history: list[dict[str, str]] | None = None) -> str | None:
    """Detecta pedidos cortos de imagen que continúan un tema visual reciente."""
    t = (text or "").strip()
    if not t or is_generate_image_intent(t) or len(t) > 120 or len(t) < 6:
        return None
    if is_casual_chat_interrupt(t):
        return None
    if _FOLLOWUP_SKIP.search(t):
        return None
    from app.services.publish_text import (
        is_explicit_social_publish_request,
        is_image_for_publish_signal,
        is_publish_help_request,
        is_publish_platform_reply,
    )

    # No llamar is_social_publish_intent aquí (recursión vía blocks_publish_intent).
    if (
        is_explicit_social_publish_request(t)
        or is_publish_platform_reply(t)
        or is_publish_help_request(t)
        or is_image_for_publish_signal(t)
    ):
        return None

    has_thread = history_has_active_image_thread(history)
    if not has_thread and not user_requests_prior_reference(t):
        return None

    recent: list[str] = []
    for row in (history or [])[-8:]:
        content = (row.get("content") or "").strip()
        if content:
            recent.append(content)
    blob = " ".join(recent[-6:]).lower()
    if not _FOLLOWUP_IMAGE_CONTEXT.search(blob) and not user_requests_prior_reference(t):
        return None
    return t


def is_pdf_intent(text: str) -> bool:
    t = text.strip()
    if len(t) < 6:
        return False
    if mentions_pdf(t):
        return True
    return any(p.search(t) for p in _PDF_PATTERNS[1:])


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
            r"^(?:genera|generar|crea|crear|exporta|exportar|convierte|convertir|guarda|guárdame|haz(me)?|dame|pon|pásalo|pasalo)\s+"
            r"(?:.{0,48}?\s+)?(?:en\s+)?(?:un(?:a)?\s+)?pdf\s*(?:de|con|sobre|que\s+diga)?\s*",
            "",
            t,
            flags=re.I,
        ).strip()

    if not content:
        content = title if title != "Documento CED" else ""

    return title[:200], content[:12000]


_PDF_FILLER_ASSISTANT = re.compile(
    r"(?:"
    r"algo\s+m[aá]s\s+en\s+lo\s+que\s+(?:le\s+)?pueda\s+ayudar"
    r"|(?:en\s+)?qu[eé]\s+m[aá]s\s+puedo\s+ayud"
    r"|(?:puedo|le)\s+puedo\s+ayudar\s+en\s+algo"
    r")",
    re.I,
)


def _is_pdf_filler_assistant(text: str) -> bool:
    t = re.sub(r"\s+", " ", (text or "").strip())
    if not t:
        return True
    if len(t) < 90 and _PDF_FILLER_ASSISTANT.search(t):
        return True
    if re.fullmatch(
        r"(?:¿?\s*)?(?:listo,?\s*señor|perfecto|de\s+nada|un\s+placer)[\s!.?]*",
        t,
        re.I,
    ):
        return True
    return False


def _assistant_texts_for_pdf(history: list[dict] | None, *, min_len: int = 80) -> list[str]:
    texts: list[str] = []
    for row in reversed(history or []):
        role = str(row.get("role") or "").lower()
        if role not in ("assistant", "model"):
            continue
        content = row.get("content")
        if not isinstance(content, str):
            continue
        text = content.strip()
        if len(text) < min_len or _is_pdf_filler_assistant(text):
            continue
        texts.append(text)
    return texts


def _last_assistant_text(history: list[dict] | None, *, min_len: int = 120) -> str:
    for text in _assistant_texts_for_pdf(history, min_len=min_len):
        return text
    return ""


def infer_pdf_title(user_text: str, content: str) -> str:
    """Título legible a partir del pedido y del cuerpo del documento."""
    blob = f"{user_text}\n{content[:900]}"
    if re.search(r"plan\s+semanal|estrategia\s+semanal", blob, re.I):
        return "Plan Semanal de Estrategia CED"
    if re.search(r"lanzamiento\s+(?:de\s+)?ced", blob, re.I):
        return "Plan de Lanzamiento CED"
    if re.search(r"\bestrategia\b", blob, re.I) and not re.search(r"tornado|noticia", blob, re.I):
        return "Estrategia CED"
    if re.search(r"\btornado\b", blob, re.I):
        if re.search(r"\bchina\b|\bhubei\b", blob, re.I):
            return "Tornado EF2 en Hubei, China"
        return "Informe sobre Tornado"
    if re.search(r"\bnoticia", blob, re.I):
        topic = re.search(
            r"noticia(?:s)?\s+(?:de|sobre|del?|la)?\s*([^.\n]{8,80})",
            user_text,
            re.I,
        )
        if topic:
            return topic.group(1).strip()[:120]
    if re.search(r"\bfinanz", blob, re.I):
        return "Reporte Financiero CED"
    body = (content or "").strip()
    for raw_line in re.split(r"[\n.!?]+", body):
        line = raw_line.strip()
        line = re.sub(r"^(?:señor,?\s*)?(?:sobre su consulta:?\s*)?", "", line, flags=re.I).strip()
        if _is_pdf_filler_assistant(line):
            continue
        if 18 <= len(line) <= 110 and not re.search(r"^(?:un momento|consulto|pdf)\b", line, re.I):
            return line[:120]
    for candidate in _assistant_texts_for_pdf(
        [{"role": "assistant", "content": body}],
        min_len=18,
    ):
        first_line = re.split(r"[\n.!?]+", candidate)[0].strip()
        if first_line and not _is_pdf_filler_assistant(first_line):
            return first_line[:120]
    return "Documento CED"


def _infer_pdf_title(user_text: str, content: str) -> str:
    return infer_pdf_title(user_text, content)


def resolve_pdf_request(
    text: str,
    history: list[dict] | None = None,
) -> tuple[str, str] | None:
    """Título y cuerpo del PDF a partir del mensaje y del historial del chat."""
    t = (text or "").strip()
    if not is_pdf_intent(t):
        return None

    parsed = parse_pdf_request(t)
    title = parsed[0] if parsed else "Documento CED"
    content = parsed[1] if parsed else ""

    pasted = re.search(r"(?:en\s+)?(?:un(?:a)?\s+)?pdf\s*\n?\s*(.+)$", t, re.I | re.S)
    if pasted:
        body = pasted.group(1).strip()
        if len(body) >= 80:
            content = body

    if len(content) < 200 and _PDF_THIS_REF.search(t):
        previous = _last_assistant_text(history, min_len=80)
        if previous:
            content = previous

    if not content or len(content) < 40:
        for previous in _assistant_texts_for_pdf(history, min_len=80):
            content = previous
            break

    if title == "Documento CED" or len(title) < 8:
        title = infer_pdf_title(t, content)

    if not content:
        return title[:200], ""

    return title[:200], content[:12000]
