"""Normalización y textos literales en español — chat, imágenes, captions (genérico)."""

from __future__ import annotations

import re
import unicodedata

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


def image_prompt_needs_verbatim_text(prompt: str, context: str = "") -> bool:
    blob = f"{prompt} {context}"
    if _IMAGE_TEXT_HINT.search(blob):
        return True
    if _TITLE_DESC_LINE.search(blob):
        return True
    if extract_quoted_phrases(blob):
        return True
    return False


def collect_image_overlay_lines(prompt: str, context: str = "") -> list[str]:
    """Reúne textos literales desde prompt + contexto (cualquier dominio)."""
    lines = extract_structured_lines(context)
    if not lines:
        lines = extract_structured_lines(prompt)
    if not lines:
        lines = overlay_lines_from_strings(extract_structured_lines(context, max_lines=8))
    if not lines:
        quotes = extract_quoted_phrases(f"{prompt}\n{context}")
        lines = quotes
    if not lines and image_prompt_needs_verbatim_text(prompt, context):
        structured = extract_structured_lines(f"{prompt}\n{context}")
        if structured:
            lines = overlay_lines_from_strings(structured)
        else:
            short = normalize_spanish(_first_phrase(prompt, max_chars=72))
            if short and len(short) >= 12:
                lines = [short]
    return lines[:5]


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
    "PROHIBIDO escribir en la imagen instrucciones del prompt, metadatos, typos del usuario "
    "ni palabras como: genera, imagen, características, referencia, instrucción, prompt."
)


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
    """Capa universal de ortografía + textos literales para CUALQUIER imagen."""
    base = (prompt or "").strip()
    if not base:
        return base
    if "TEXTOS EXACTOS" in base:
        if _ORTHOGRAPHY_RULE.split(".")[0] not in base:
            return f"{base} {_ORTHOGRAPHY_RULE}"
        return base

    overlay = collect_image_overlay_lines(base, context)
    headline = build_image_headline(context, overlay[0] if overlay else base[:60])

    if overlay or image_prompt_needs_verbatim_text(base, context):
        verbatim = format_verbatim_image_copy(overlay, headline=headline or None)
        if verbatim:
            return (
                f"{base} {_ORTHOGRAPHY_RULE} {verbatim} "
                "Prefiere tipografía grande y clara; máximo una frase corta (≤12 palabras) "
                "si el texto es largo. Mejor poco texto correcto que un párrafo ilegible."
            )

    return f"{base} {_ORTHOGRAPHY_RULE} Minimiza texto incrustado salvo que el pedido lo exija."


IMAGE_EMBEDDED_TEXT_DISCLAIMER = (
    "Señor, aviso: el texto dentro de imágenes generadas por IA (modelo actual: "
    "Gemini 2.5 Flash Image) suele no salir perfectamente legible. "
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
