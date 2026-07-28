"""Normalización y textos literales en español — chat, imágenes, captions (genérico)."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

# Correcciones frecuentes (usuario, voz, transcripción o modelos de imagen).
_TYPO_MAP: dict[str, str] = {
    "veneficio": "beneficio",
    "veneficios": "beneficios",
    "caracteristicas": "características",
    "immune": "inmune",
    "intesino": "intestino",
    "equilibibals": "equilibrada",
    "equilibibal": "equilibrada",
    "nuturcion": "nutrición",
    "nutricion": "nutrición",
    "digestsion": "digestión",
    "digestsión": "digestión",
    "optimo": "óptimo",
    "optima": "óptima",
    "energia": "energía",
    "proteccion": "protección",
    "absorcion": "absorción",
}

_ENGLISH_REPLACEMENTS = {
    "immune": "inmune",
    "digestion": "digestión",
    "nutrition": "nutrición",
    "energy": "energía",
    "health": "salud",
}

_TITLE_DESC_LINE = re.compile(
    r"(?:^|\n)\s*(?:[\*\-•]\s*)?"
    r"([A-Za-zÁÉÍÓÚáéíóúÑñ0-9][A-Za-zÁÉÍÓÚáéíóúÑñ0-9\s]{2,35}) *: +"
    r"(.{8,160}?)(?=\n|$|\*|\-|\•|[A-ZÁÉÍÓÚ][a-záéíóú]+:)",
    re.M,
)
_SKIP_LINE_TITLES = frozenset(
    {
        "características",
        "caracteristicas",
        "beneficios",
        "ventajas",
        "principales beneficios",
        "principales beneficios son",
        "principales ventajas",
        "principales ventajas son",
        "sus principales beneficios son",
        "sus principales ventajas son",
        "puntos clave",
        "puntos clave son",
        "aspectos principales",
        "programa incluye",
        "incluye",
        "referencia",
        "información",
        "informacion",
        "nota",
        "ejemplo",
        "contexto",
    },
)
_IMAGE_TEXT_HINT = re.compile(
    r"\b("
    r"texto|escrito|frase|t[ií]tulo|caption|flyer|banner|letras|nombre|"
    r"quote|cita|eslogan|headline|subtitulo|subt[ií]tulo|"
    r"beneficios|veneficios|ventajas|puntos?\s+clave|especificaciones|caracter[ií]sticas|"
    r"agenda|horarios?|m[oó]dulos?|programa|invitaci[oó]n|promoci[oó]n|"
    r"publicidad|anuncio|post|vender|vendiendo|evento|curso|taller|servicio"
    r")\b",
    re.I,
)
_ORTHOGRAPHY_RULE = (
    "Ortografía española impecable en todo texto visible. "
    "Sin anglicismos innecesarios ni palabras inventadas."
)


def _replace_word_preserve_case(word: str, replacement: str) -> str:
    if not word:
        return replacement
    if word.isupper():
        return replacement.upper()
    if word[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def _apply_typo_fixes(text: str) -> str:
    def fix_word(match: re.Match[str]) -> str:
        word = match.group(0)
        lower = word.lower()
        for wrong, right in _TYPO_MAP.items():
            if lower == wrong:
                return _replace_word_preserve_case(word, right)
        for eng, spa in _ENGLISH_REPLACEMENTS.items():
            if lower == eng:
                return _replace_word_preserve_case(word, spa)
        return word

    return re.sub(r"\b[\w\-áéíóúñü]+\b", fix_word, text, flags=re.I)


def normalize_spanish(text: str) -> str:
    """Corrige typos comunes y normaliza espacios sin alterar nombres propios."""
    t = unicodedata.normalize("NFC", (text or "").strip())
    if not t:
        return t
    t = re.sub(r"\s+", " ", t)
    return _apply_typo_fixes(t)


def sanitize_label(text: str) -> str:
    clean = normalize_spanish(text.strip())
    clean = re.sub(r"\s+", " ", clean)
    if not clean:
        return clean
    return clean[0].upper() + clean[1:]


sanitize_benefit_title = sanitize_label  # compat


def _first_phrase(desc: str, *, max_chars: int = 48) -> str:
    text = normalize_spanish(desc)
    text = re.split(r"[.;]\s", text, maxsplit=1)[0].strip()
    if len(text) > max_chars:
        text = text[: max_chars - 1].rsplit(" ", 1)[0].strip()
    return text


def compact_overlay_line(title: str, desc: str) -> str:
    """Línea corta para gráfico — aplica a cualquier tema (producto, evento, servicio…)."""
    label = sanitize_label(title)
    phrase = _first_phrase(desc, max_chars=44)
    if not phrase:
        return label
    if len(f"{label}: {phrase}") > 58:
        return label
    return f"{label}: {phrase}"


def _normalize_structured_blob(text: str) -> str:
    """Separa viñetas en línea («A: x. B: y.») para extracción fiable en cualquier tema."""
    t = (text or "").strip()
    if not t:
        return t
    # Intro genérico («puntos clave son: A: …») → líneas separadas
    t = re.sub(
        r":\s+(?=[A-ZÁÉÍÓÚÑ0-9][A-Za-zÁÉÍÓÚáéíóúÑñ0-9\s]{2,32}\s*:)",
        ":\n",
        t,
    )
    t = re.sub(
        r"\.\s+(?=[A-ZÁÉÍÓÚÑ0-9][A-Za-zÁÉÍÓÚáéíóúÑñ0-9\s]{2,32}\s*:)",
        ".\n",
        t,
    )
    t = re.sub(r" *: +", ": ", t)
    return t


_normalize_benefit_blob = _normalize_structured_blob  # compat


def extract_structured_lines(text: str, *, max_lines: int = 5) -> list[str]:
    """Extrae líneas «Título: descripción» de cualquier texto."""
    lines: list[str] = []
    for match in _TITLE_DESC_LINE.finditer(_normalize_structured_blob(text or "")):
        title = sanitize_label(match.group(1).strip())
        desc = normalize_spanish(re.sub(r"\s+", " ", match.group(2).strip()))
        if title.lower() in _SKIP_LINE_TITLES:
            continue
        if len(desc) < 8:
            continue
        line = compact_overlay_line(title, desc)
        if line and line not in lines:
            lines.append(line)
        if len(lines) >= max_lines:
            break
    return lines


def extract_structured_lines_from_history(
    history: list[dict[str, str]] | None,
    *,
    max_lines: int = 5,
) -> list[str]:
    for row in reversed(history or []):
        role = str(row.get("role") or "")
        if role not in ("model", "assistant"):
            continue
        lines = extract_structured_lines(str(row.get("content") or ""), max_lines=max_lines)
        if lines:
            return lines
    return []


def extract_quoted_phrases(text: str, *, max_phrases: int = 5) -> list[str]:
    phrases: list[str] = []
    for match in re.finditer(r'["«“]([^"»”]{4,80})["»”]', text or ""):
        phrase = normalize_spanish(match.group(1).strip())
        if phrase and phrase not in phrases:
            phrases.append(phrase)
        if len(phrases) >= max_phrases:
            break
    return phrases


def overlay_lines_from_strings(bullets: list[str]) -> list[str]:
    lines: list[str] = []
    for bullet in bullets:
        if ":" in bullet:
            title, _, desc = bullet.partition(":")
            line = compact_overlay_line(title, desc)
        else:
            line = sanitize_label(bullet)
        line = normalize_spanish(line)
        if line and line not in lines:
            lines.append(line)
        if len(lines) >= 5:
            break
    return lines


overlay_lines_from_benefit_strings = overlay_lines_from_strings  # compat


def build_image_headline(context: str = "", subject: str = "") -> str:
    """Titular genérico para imagen — deriva del tema o del contexto."""
    skip = {
        "producto",
        "el producto",
        "tema",
        "el tema",
        "imagen",
        "creativo",
        "en el fondo",
        "referencia",
        "evento",
        "servicio",
    }
    subj = sanitize_label(subject)
    if subj and subj.lower() not in skip and not re.search(r"\bfondo\b", subj, re.I):
        if len(subj) <= 60:
            return subj
    for block in (context or "").split("\n"):
        line = block.strip()
        if len(line) < 12:
            continue
        sentence = normalize_spanish(line.split(".")[0].strip())
        if 12 <= len(sentence) <= 72:
            return sentence
    return ""


build_flyer_headline = build_image_headline  # compat


_IDEOGRAM_EXPLICIT_TEXT_REQUEST = re.compile(
    r"\b(?:"
    r"que\s+diga[n]?|que\s+ponga[n]?|con\s+el\s+texto|con\s+la\s+frase|"
    r"con\s+las?\s+palabras?|el\s+texto\s+debe\s+decir|letras?\s+que\s+diga[n]?|"
    r"detalles?\s+escritos?|textos?\s+(?:exactos?|literales?|visibles?|legibles?)|"
    r"(?:deben|debe|tienen|tiene|tienen\s+que|tiene\s+que)\s+"
    r"(?:ir|aparecer|estar|llevar|incluir)\s+"
    r"(?:escritos?|el\s+texto|los\s+textos?|en\s+la\s+imagen|las?\s+etiquetas?)|"
    r"escrito(?:s)?\s+en\s+la\s+imagen|texto(?:s)?\s+en\s+la\s+imagen|"
    r"etiquetas?\s+(?:con\s+texto|escritas?|legibles?)|"
    r"tipograf[ií]a\s+legible|con\s+los\s+textos?\s+(?:en|de)\s+la\s+imagen|"
    r"manten(?:iendo|er|me|gas|ga|gamos)?\s+(?:l[ao]s?\s+)?textos?|"
    r"mant[eé]n(?:me|iendo|gas|ga)?\s+(?:l[ao]s?\s+)?textos?|"
    r"conserv(?:a|ando|ar|e)\s+(?:l[ao]s?\s+)?textos?|"
    r"con\s+(?:l[ao]s?\s+)?mismos?\s+textos?|"
    r"sin\s+quitar\s+(?:l[ao]s?\s+)?textos?|"
    r"quiero\s+que\s+mantengas\s+(?:l[ao]s?\s+)?textos?"
    r")\b",
    re.I,
)


def prompt_requires_ideogram_text(prompt: str) -> bool:
    """Señal ESTRICTA de texto literal a renderizar — para enrutar hacia un proveedor
    de pago (Ideogram), NO para decorar el prompt de Gemini.

    A propósito NO reutiliza `image_prompt_needs_verbatim_text`: esa función es amplia
    por diseño (dispara con palabras genéricas de marketing como "beneficios", "evento"
    o "servicio" para añadir instrucciones de texto a Gemini, donde un falso positivo
    solo agrega una frase al prompt). Aquí un falso positivo significa gastar dinero
    real en una llamada a Ideogram sin necesidad, así que solo señales fuertes:
    comillas, "que diga/ponga X", "mantener los textos", tipografía legible pedida.

    Solo mira el pedido ACTUAL del usuario (nunca el historial/contexto de chat) para
    no heredar comillas o títulos de turnos anteriores no relacionados con este pedido.
    """
    t = (prompt or "").strip()
    if not t:
        return False
    if extract_quoted_phrases(t):
        return True
    return bool(_IDEOGRAM_EXPLICIT_TEXT_REQUEST.search(t))


def extract_spoken_overlay_labels(text: str, *, max_lines: int = 6) -> list[str]:
    """Extrae etiquetas UI dichas en prosa («creador es X», «asistente virtual», etc.)."""
    t = (text or "").strip()
    if not t:
        return []
    lines: list[str] = []

    def _add(label: str) -> None:
        clean = sanitize_label(label)
        if not clean or _looks_like_prompt_instruction(clean):
            return
        if clean not in lines:
            lines.append(clean)

    for match in re.finditer(
        r"(?is)\bcreador(?:\s+es|\s*:)\s*"
        r"([A-Za-zÁÉÍÓÚáéíóúÑñ][\wÁÉÍÓÚáéíóúÑñ]*(?:\s+[A-Za-zÁÉÍÓÚáéíóúÑñ][\wÁÉÍÓÚáéíóúÑñ]*){0,4})",
        t,
    ):
        name = match.group(1).strip().rstrip(".,;")
        # Cortar si se coló prosa («que este sistema…»).
        name = re.split(r"\s+que\s+", name, maxsplit=1, flags=re.I)[0].strip()
        if 3 <= len(name) <= 48:
            _add(f"Creador: {name}")
    for match in re.finditer(
        r"(?is)\b(?:que\s+es|donde\s+dice\s+que\s+es|dice\s+que\s+es)\s+"
        r"(?:un[oa]?\s+)?(asistente\s+virtual)\b",
        t,
    ):
        _add(match.group(1))
    if re.search(r"(?is)\basistente\s+virtual\b", t):
        _add("Asistente Virtual")
    if re.search(
        r"(?is)\bgener(?:a|aci[oó]n|ar)\s+(?:de\s+)?im[aá]genes?\s+(?:y\s+)?pdfs?\b",
        t,
    ):
        _add("Generación de imágenes y PDF")
    if re.search(
        r"(?is)\b(?:c[aá]mara|vision|visi[oó]n).{0,40}\ban[aá]lisis\b|"
        r"\bsistema\s+avanzado\s+con\b|"
        r"\bcon\s+(?:clavo\s+)?c[aá]mara\b",
        t,
    ):
        _add("Sistema avanzado con cámara, visión y análisis")
    if re.search(r"(?is)\bmemoria\s+persistente\b", t):
        _add("Memoria persistente")
    if re.search(r"(?is)\ban[aá]lisis\s+financiero\b", t):
        _add("Análisis financiero")
    if re.search(r"(?is)\bmonitoreo\s+de\s+redes\s+sociales\b", t):
        _add("Monitoreo de redes sociales")
    if re.search(r"(?is)\bventas\s+y\s+marketing\b", t):
        _add("Ventas y marketing digital")

    # Viñetas / checklist del propio mensaje del asistente («- ✅ Asistente Virtual»)
    for match in re.finditer(
        r"(?m)^\s*(?:[\-\*•]|\d+[.)]|✅)\s*(?:\*\*)?(.{4,60}?)(?:\*\*)?\s*$",
        t,
    ):
        raw = re.sub(r"[✅\*]+", "", match.group(1)).strip()
        if raw:
            _add(raw)

    return lines[:max_lines]


def image_prompt_needs_verbatim_text(prompt: str, context: str = "") -> bool:
    blob = f"{prompt} {context}"
    if _IMAGE_TEXT_HINT.search(blob):
        return True
    if _TITLE_DESC_LINE.search(blob):
        return True
    if extract_quoted_phrases(blob):
        return True
    return False


_INSTRUCTIONAL_OVERLAY = re.compile(
    r"(?is)\b(?:"
    r"escena\s+pedida|tomando\s+en\s+cuenta|la\s+imagen\s+que\s+sea|"
    r"es\s+algo\s+as[ií]|"
    r"(?:me\s+)?genera(?:r|me|mos|s|is|n|d)?\s+(?:una?\s+)?"
    r"(?:imagen|foto|ilustraci[oó]n|dise[nñ]o|creativo|banner|flyer)|"
    r"(?:ok\s+|ahora\s+)*(?:me\s+)?genera(?:r|me|s)?\b|"
    r"haz(?:me)?\s+(?:una?\s+)?(?:imagen|foto)|"
    r"crea(?:r|me|s)?\s+(?:una?\s+)?(?:imagen|foto)|"
    r"debe(?:n)?\s+ir\s+escrit|"
    r"instrucci[oó]n(?:es)?\s+actuales|referencia\s+visual|\bprompt\b"
    r")\b"
)

# Solo mezclar historial en overlays cuando el turno actual lo pide.
_CONTEXT_OVERLAY_OPT_IN = re.compile(
    r"(?is)\b(?:"
    r"estos?\s+detalles|"
    r"detalles?\s+(?:resumidos\s+)?escritos?|"
    r"(?:con|usa|usando|incluye|incluyendo)\s+(?:estos?\s+)?(?:textos?|titulares?|etiquetas?)|"
    r"mant[eé]n(?:me|gas|ga|iendo)?\s+(?:l[ao]s?\s+)?textos?|"
    r"conserv(?:a|ando)\s+(?:l[ao]s?\s+)?textos?|"
    r"las?\s+caracter[ií]sticas|"
    r"que\s+diga|que\s+ponga|con\s+el\s+t[ií]tulo"
    r")\b"
)


def _prompt_allows_context_overlays(prompt: str) -> bool:
    """True solo si el pedido actual pide tipografía del historial/lista previa."""
    t = (prompt or "").strip()
    if not t:
        return False
    if prompt_requires_ideogram_text(t):
        return True
    return bool(_CONTEXT_OVERLAY_OPT_IN.search(t))


def _looks_like_prompt_instruction(text: str) -> bool:
    t = (text or "").strip()
    if len(t) < 4:
        return True
    if _INSTRUCTIONAL_OVERLAY.search(t):
        return True
    # Pedidos largos en prosa no son etiquetas de UI.
    if len(t) > 64 and not re.search(r"[:\-•]", t):
        return True
    # Saludos / filler del chat que a veces se colaban vía ALL-CAPS + historial.
    if re.fullmatch(r"(?i)hola|buenas|ok|vale|listo|gracias|se[nñ]or", t):
        return True
    return False


def extract_bullet_labels(text: str, *, max_lines: int = 5) -> list[str]:
    """Extrae viñetas («- Título», «• Título», «- **Título** — desc»).

    NO cosecha frases en MAYÚSCULAS del pedido («ME GENERAS UNA IMAGEN…»): eso
    convertía el prompt entero en TEXTOS EXACTOS y Gemini lo pintaba en la foto.
    """
    lines: list[str] = []
    source = text or ""
    for match in re.finditer(
        r"(?m)^\s*(?:[\-\*•]|\d+[.)])\s+(?:\*\*)?(.+?)(?:\*\*)?\s*$",
        source,
    ):
        raw = match.group(1).strip()
        # «**Título** — descripción» o «Título — descripción»
        raw = re.sub(r"\*+", "", raw).strip()
        if "—" in raw:
            raw = raw.split("—", 1)[0].strip()
        elif " - " in raw and len(raw) > 40:
            raw = raw.split(" - ", 1)[0].strip()
        label = sanitize_label(raw.rstrip(".;,"))
        if not label or _looks_like_prompt_instruction(label):
            continue
        if label.lower() in _SKIP_LINE_TITLES:
            continue
        if label not in lines:
            lines.append(label)
        if len(lines) >= max_lines:
            return lines
    return lines[:max_lines]


def collect_image_overlay_lines(prompt: str, context: str = "") -> list[str]:
    """Reúne textos literales a pintar — desde el pedido actual; historial solo con opt-in.

    Nunca convierte instrucciones del usuario («ME GENERAS UNA IMAGEN…») ni viñetas
    de turnos anteriores (capacidades CED) en tipografía, salvo que el usuario pida
    explícitamente detalles/textos escritos.
    """
    use_context = _prompt_allows_context_overlays(prompt)
    ctx = (context or "") if use_context else ""
    blob = f"{prompt}\n{ctx}".strip() if ctx else (prompt or "")

    lines: list[str] = []
    if use_context and ctx:
        lines = extract_structured_lines(ctx)
        if not lines:
            lines = overlay_lines_from_strings(extract_structured_lines(ctx, max_lines=8))
    if not lines:
        lines = extract_structured_lines(prompt)
    if not lines:
        lines = extract_quoted_phrases(blob)
    if not lines:
        lines = extract_bullet_labels(blob)
    spoken = extract_spoken_overlay_labels(blob)
    for label in spoken:
        if label not in lines:
            lines.append(label)
    cleaned = [ln for ln in lines if ln and not _looks_like_prompt_instruction(ln)]
    if cleaned:
        return summarize_overlay_labels_for_image(cleaned, max_labels=5)
    # Sin líneas de contenido reales: no inventar tipografía a partir del pedido.
    return []


def summarize_overlay_labels_for_image(
    lines: list[str],
    *,
    max_labels: int = 5,
    max_chars: int = 36,
) -> list[str]:
    """Acorta etiquetas para tipografía legible (no párrafos enteros)."""
    out: list[str] = []
    for raw in lines:
        label = sanitize_label(raw)
        # Markdown «**Título** — descripción» → solo el título.
        label = re.sub(r"\*+", "", label).strip()
        if "—" in label:
            label = label.split("—", 1)[0].strip()
        elif " - " in label and len(label) > max_chars:
            label = label.split(" - ", 1)[0].strip()
        if ":" in label and len(label) > max_chars:
            left, _, right = label.partition(":")
            label = left.strip() if len(left.strip()) >= 4 else label
            _ = right
        label = re.sub(r"\s+", " ", label).strip(" .;,")
        if len(label) > max_chars:
            label = label[: max_chars - 1].rsplit(" ", 1)[0].strip()
        if len(label) < 3 or _looks_like_prompt_instruction(label):
            continue
        # Evitar nombres de tools / API en el HUD.
        if re.search(
            r"(?i)\b(?:search_web|generate_image|save_memory|recall_memory|"
            r"activar_prospeccion|publicar_facebook|publicar_instagram|"
            r"analyze_camera|generar_pdf)\b",
            label,
        ):
            continue
        if label not in out:
            out.append(label)
        if len(out) >= max_labels:
            break
    return out


_CED_BRAND_REQUEST = re.compile(
    r"(?is)\b(?:"
    r"sistema\s+ced\b|"
    r"\bced\b|"
    r"castillo\s+de\s+la\s+evoluci[oó]n|"
    r"marca\s+ced|"
    r"logo\s+(?:de\s+)?ced|"
    r"branding\s+ced|"
    r"infograf[ií]a\s+(?:del\s+)?(?:sistema\s+)?ced"
    r")\b"
)


def user_requests_ced_branding(text: str) -> bool:
    """True solo si el pedido menciona CED / la marca de forma explícita."""
    return bool(_CED_BRAND_REQUEST.search(text or ""))


def _faithful_visual_expansion(visual: str, *, has_reference: bool = False) -> str:
    """Expande el sujeto del usuario sin inyectar marca CED ni estilo de producto."""
    subject = (visual or "").strip(" ,.;")
    if has_reference:
        if subject:
            return (
                f"{subject}. Conserva el estilo y la composición de la imagen de referencia; "
                "alta calidad, iluminación coherente, resultado profesional."
            )
        return (
            "Variación fiel de la imagen de referencia según el pedido del usuario; "
            "alta calidad, sin cambiar el tema a otra marca o producto."
        )
    if subject:
        return (
            f"{subject}. Alta calidad, composición clara, buena iluminación, "
            "detalle nítido, resultado profesional fiel al sujeto pedido."
        )
    return (
        "Imagen de alta calidad fiel al pedido del usuario, composición clara, "
        "buena iluminación, sin añadir marcas, logos ni temas ajenos."
    )


def _ced_branded_visual(*, has_reference: bool = False) -> str:
    """Brief de marca CED — solo cuando el usuario lo pidió explícitamente."""
    if has_reference:
        return (
            "Variación de la imagen de referencia con identidad CED "
            "(futurista, HUD holográfico, paleta cian/azul); tipografía clara si aplica."
        )
    return (
        "Infografía premium del sistema CED, estilo futurista, HUD holográfico, "
        "paleta cian y azul oscuro, tipografía grande y legible"
    )


def orchestrate_image_generation_brief(
    user_text: str,
    *,
    context: str = "",
    has_reference: bool = False,
) -> dict[str, Any]:
    """Orquestador: expansión fiel al pedido; marca CED solo si el usuario la pide.

    Por defecto NO inyecta branding/sistema CED. Solo aplica identidad CED cuando
    el mensaje menciona CED / Castillo de la Evolución / logo CED de forma explícita,
    o cuando pide «detalles escritos» y el contexto trae contenido de marca CED.
    """
    raw = (user_text or "").strip()
    from app.services.gemini_images import (
        strip_image_generation_instruction,
        strip_image_prompt_meta,
    )

    visual = strip_image_prompt_meta(strip_image_generation_instruction(raw))
    # Quitar bloques markdown enormes del brief visual; las etiquetas van aparte.
    visual = re.sub(r"(?m)^#{1,3}\s+.*$", " ", visual)
    visual = re.sub(r"(?m)^\s*[-*•]\s+\*\*.*$", " ", visual)
    visual = re.sub(r"\s+", " ", visual).strip(" ,.;")
    if len(visual) > 280:
        visual = visual[:279].rsplit(" ", 1)[0].strip()

    explicit_text = prompt_requires_ideogram_text(raw)
    overlays = collect_image_overlay_lines(raw, context)
    wants_text = bool(overlays) or explicit_text
    # Logo / marca pedida en escena NO implica TEXTOS EXACTOS del historial.
    logo_only = bool(re.search(r"(?i)\blogo\b", raw) and not wants_text)

    wants_ced = user_requests_ced_branding(raw) or (
        bool(overlays) and user_requests_ced_branding(context or "")
    )
    details_only = bool(
        re.search(r"(?i)^estos?\s+detalles\b", visual)
        or re.search(r"(?i)\bdetalles\s+resumidos\s+escritos\b", visual)
        or re.search(r"(?i)^estas?\s+caracter[ií]sticas\b", visual)
    )

    if details_only:
        # Pedido del tipo «con estos detalles» sin sujeto visual propio.
        if wants_ced:
            visual = _ced_branded_visual(has_reference=has_reference)
        elif overlays:
            visual = (
                "Composición visual clara y profesional que ilustra los puntos indicados; "
                "fondo limpio, jerarquía visual legible, sin marcas ajenas al pedido."
            )
        else:
            visual = _faithful_visual_expansion("", has_reference=has_reference)
    elif not visual:
        visual = (
            _ced_branded_visual(has_reference=has_reference)
            if wants_ced
            else _faithful_visual_expansion("", has_reference=has_reference)
        )
    elif wants_ced and not re.search(r"(?i)\bced\b|castillo\s+de\s+la\s+evoluci", visual):
        # Usuario pidió CED pero el strip dejó poco; reforzar identidad sin borrar el sujeto.
        visual = f"{visual}. Identidad visual CED, estilo futurista, paleta cian/azul."
    else:
        # Sujeto presente (aunque sea corto: «un perro», «un atardecer»): expansión fiel.
        # NUNCA sustituir por branding CED.
        visual = _faithful_visual_expansion(visual, has_reference=has_reference)

    parts = [visual]
    if has_reference:
        parts.append("Usa la imagen adjunta solo como referencia de estilo/composición.")
    if overlays:
        parts.append(format_verbatim_image_copy(overlays))
        parts.append(_CREATIVE_NO_LEAK)
        parts.append(
            "Tipografía grande, alto contraste, máximo 5 etiquetas cortas; "
            "PROHIBIDO pintar el pedido del usuario o instrucciones del sistema."
        )
    elif wants_text:
        # Tipografía pedida sin líneas concretas (p.ej. mantener textos de referencia).
        parts.append(_CREATIVE_NO_LEAK)
        parts.append(
            "Incluye tipografía legible en español si aplica; "
            "PROHIBIDO pintar el pedido del usuario, saludos del chat o listas de capacidades."
        )
    else:
        # Escena pura (modo avanzado + chat): nunca pintar el prompt ni saludos.
        parts.append(
            "Sin texto, tipografía, subtítulos, marcas de agua, etiquetas, "
            "viñetas ni frases del pedido del usuario en la imagen."
        )
        if logo_only:
            parts.append(
                "Si se pide logo de marca, intégralo como marca gráfica pequeña; "
                "no escribas el pedido ni listas de capacidades."
            )

    return {
        "visual_brief": visual,
        "overlay_lines": overlays,
        "wants_literal_text": wants_text,
        "technical_prompt": " ".join(p for p in parts if p).strip()[:3800],
    }


def format_verbatim_image_copy(lines: list[str], *, headline: str | None = None) -> str:
    """Bloque de instrucción con textos literales para modelos de imagen."""
    all_lines = [normalize_spanish(line) for line in lines if line.strip()]
    if headline:
        head = normalize_spanish(headline)
        if head and head not in all_lines:
            all_lines.insert(0, head)
    if not all_lines:
        return ""
    quoted = [f'"{line}"' for line in all_lines]
    return (
        "TEXTOS EXACTOS EN ESPAÑOL (ortografía obligatoria — copiar CARÁCTER POR CARÁCTER; "
        "no parafrasear, no inventar palabras, no mezclar inglés):\n"
        + "\n".join(f"- {q}" for q in quoted)
        + "\nSi no puedes renderizar texto perfecto, usa MENOS texto pero sin errores ortográficos."
    )


_CREATIVE_NO_LEAK = (
    "PROHIBIDO renderizar como tipografía meta-instrucciones del brief, pedidos del "
    "usuario, metadatos o frases de control del sistema. Solo tipografía de contenido "
    "(títulos/etiquetas de producto o UI)."
)

_PROMPT_META_LEAK = re.compile(
    r"(?is)\b(?:"
    r"instrucciones\s+actuales\s+del\s+usuario(?:\s*\([^)]*\))?|"
    r"instrucciones\s+adicionales\s+del\s+usuario(?:\s*\([^)]*\))?|"
    r"contexto\s+reciente\s+del\s+chat|"
    r"an[aá]lisis\s+previo\s+de\s+la\s+imagen[^\n:]*|"
    r"genera\s+una\s+imagen\s+de\s+alta\s+calidad\s+seg[uú]n\s+este\s+pedido|"
    r"escena\s+pedida|"
    r"cambios?\s+pedidos?|"
    r"edici[oó]n\s+de\s+la\s+imagen(?:\s+(?:adjunta|de\s+referencia))?"
    r")\s*:?\s*"
)


def strip_prompt_meta_for_image(text: str) -> str:
    """Quita wrappers internos que los modelos de imagen suelen pintar como tipografía."""
    t = (text or "").strip()
    if not t:
        return ""
    prev = None
    while prev != t:
        prev = t
        t = _PROMPT_META_LEAK.sub(" ", t)
        t = re.sub(r"\bReferencia:\s*", " ", t, flags=re.I)
        # Frases de control del usuario que Nano Banana pinta literalmente.
        # No consumir el contenido útil después de «detalles escritos: …».
        t = re.sub(
            r"(?is)\b(?:la\s+imagen\s+que\s+sea\s+as[ií]|es\s+algo\s+as[ií])\b[,.]?\s*",
            " ",
            t,
        )
        t = re.sub(
            r"(?is)\btomando\s+en\s+cuenta\s+que\s+(?:en\s+la\s+imagen\s+)?"
            r"(?:deben|debe|tienen|tiene)\s+(?:ir|aparecer|estar)\s+"
            r"(?:los\s+)?detalles?\s+escritos?\s*:?\s*",
            " ",
            t,
        )
        t = re.sub(r"[ \t]{2,}", " ", t)
        t = re.sub(r"\n{3,}", "\n\n", t).strip(" \n,.;:")
    return t


def format_creative_image_copy(
    lines: list[str],
    *,
    headline: str | None = None,
    max_lines: int = 4,
) -> str:
    """Textos cortos para flyer — solo titulares; evita párrafos ilegibles en Gemini."""
    short: list[str] = []
    for line in lines:
        if ":" in line:
            short.append(sanitize_label(line.split(":", 1)[0]))
        else:
            short.append(sanitize_label(line[:32]))
        if len(short) >= max_lines:
            break
    if headline:
        head = sanitize_label(headline)
        if head and head.lower() not in {s.lower() for s in short}:
            short.insert(0, head)
    short = short[:max_lines]
    if not short:
        return ""
    quoted = [f'"{line}"' for line in short]
    return (
        f"{_CREATIVE_NO_LEAK}\n"
        "TEXTOS EXACTOS EN LA IMAGEN (una línea cada uno; copiar tal cual):\n"
        + "\n".join(f"- {q}" for q in quoted)
        + "\nSi no puedes escribir perfecto, usa solo el titular y 2 viñetas cortas."
    )


def augment_image_prompt(prompt: str, context: str = "") -> str:
    """Capa de brief visual: anti-fuga + textos literales SOLO si el pedido los exige."""
    base = strip_prompt_meta_for_image((prompt or "").strip())
    if not base:
        return base
    ctx = strip_prompt_meta_for_image(context or "")
    if "TEXTOS EXACTOS" in base:
        if _ORTHOGRAPHY_RULE.split(".")[0] not in base:
            return f"{base} {_ORTHOGRAPHY_RULE} {_CREATIVE_NO_LEAK}"
        if "PROHIBIDO escribir" not in base:
            return f"{base} {_CREATIVE_NO_LEAK}"
        return base

    overlay = collect_image_overlay_lines(base, ctx)
    headline = build_image_headline(ctx, overlay[0] if overlay else base[:60])

    if overlay or image_prompt_needs_verbatim_text(base, ctx):
        verbatim = format_verbatim_image_copy(overlay, headline=headline or None)
        if verbatim:
            return (
                f"{base} {_ORTHOGRAPHY_RULE} {verbatim} {_CREATIVE_NO_LEAK} "
                "Prefiere tipografía grande y clara; máximo una frase corta (≤12 palabras) "
                "si el texto es largo. Mejor poco texto correcto que un párrafo ilegible."
            )
        # Pedido de tipografía sin líneas concretas: conservar/mejorar textos de la
        # referencia; NUNCA pintar el pedido del usuario como tipografía.
        return (
            f"{base} {_ORTHOGRAPHY_RULE} {_CREATIVE_NO_LEAK} "
            "Incluye tipografía legible en español. Si hay imagen de referencia con "
            "etiquetas o títulos, reprodúcelos con ortografía correcta. "
            "No escribas en la imagen el pedido del usuario ni frases meta."
        )

    # Escena pura: NO mencionar «instrucciones/usuario/pedido» (el modelo las pinta).
    # NO hablar de «texto visible» si no pedimos tipografía.
    return (
        f"{base}. "
        "Sin texto, tipografía, subtítulos, marcas de agua ni etiquetas en la imagen."
    )

IMAGE_EMBEDDED_TEXT_DISCLAIMER = (
    "Señor, aviso: el texto dentro de imágenes generadas por IA (modelo actual: "
    "Nano Banana 2 / Gemini 3.1 Flash Image) suele no salir perfectamente legible. "
    "Aquí está el resultado:"
)


def with_image_text_disclaimer(reply: str, prompt: str, context: str = "") -> str:
    """Aviso honesto cuando el pedido incluye texto visible en la imagen."""
    body = (reply or "").strip()
    if not body:
        return body
    if not image_prompt_needs_verbatim_text(prompt, context):
        return body
    if "aviso:" in body.lower() and "legible" in body.lower():
        return body
    return f"{IMAGE_EMBEDDED_TEXT_DISCLAIMER}\n\n{body}"


def polish_spanish_for_user(text: str) -> str:
    """Pulido ortográfico para cualquier respuesta visible al usuario."""
    raw = (text or "").strip()
    if not raw:
        return raw
    paragraphs = re.split(r"\n\s*\n", raw)
    polished: list[str] = []
    for block in paragraphs:
        lines = block.split("\n")
        fixed_lines = [normalize_spanish(line) if line.strip() else line for line in lines]
        polished.append("\n".join(fixed_lines))
    return "\n\n".join(polished)
