"""Normalización y textos literales en español — chat, imágenes, captions (genérico)."""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Literal

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
    "prospeccion": "prospección",
    "prosaeccion": "prospección",
    "prosaecion": "prospección",
    "prosaeción": "prospección",
    "i4": "IA",
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
    r"(?i)\b(?:"
    # Señales POSITIVAS de tipografía pedida (nunca «sin texto»).
    r"con\s+texto|texto\s+(?:que\s+diga|visible|legible|escrito)|"
    r"que\s+diga|que\s+ponga|escrito\s+en\s+la\s+imagen|"
    r"t[ií]tulo|caption|flyer|banner|letras|nombre\s+del\s+producto|"
    r"quote|cita|eslogan|headline|subtitulo|subt[ií]tulo|"
    r"beneficios|veneficios|ventajas|puntos?\s+clave|especificaciones|caracter[ií]sticas|"
    r"agenda|horarios?|m[oó]dulos?|programa|invitaci[oó]n|promoci[oó]n|"
    r"publicidad|anuncio|post\s+para|vender|vendiendo|evento|curso|taller|servicio"
    r")\b"
)
_SCENE_FORBIDS_TEXT = re.compile(
    r"(?i)\b(?:"
    r"sin\s+texto|"
    r"no\s+(?:dibujes|renderices|incluyas|pongas)\s+texto|"
    r"without\s+text|no\s+text(?:\s|,|\.|$)|"
    r"no\s+letters|no\s+typography|"
    r"ninguna\s+letra|ninguna\s+palabra|ni\s+tipograf"
    r")\b"
)
_ORTHOGRAPHY_RULE = (
    "Ortografía española impecable en todo texto visible. "
    "Frases completas y correctamente escritas, sin errores tipográficos ni letras faltantes. "
    "Sin anglicismos innecesarios ni palabras inventadas."
)
_FRAME_SAFE_RULE = (
    "FULL FRAME / SAFE AREA: keep the entire composition and ALL on-image text fully "
    "inside the canvas with generous inner margins (about 10% safe zone). Center the "
    "main subject and every word. Nothing cropped or clipped by the edges — no cut-off "
    "objects, no truncated letters."
)
_SPELLING_STRICT_RULE = (
    "SPELLING: every visible word must be complete and correctly spelled. "
    "Copy requested Spanish words character-by-character "
    "(never drop, swap, or invent letters; keep every vowel, including the u in equipo). "
    "Incomplete or misspelled words are forbidden. "
    'If the word is IA, write the letters I and A — never the digit 4 (never "I4"). '
    'If the word is Prospección, spell P-r-o-s-p-e-c-c-i-ó-n — never "Prosaeccion". '
    'If the brand is CED, write the letters C then E then D in that order — never SEC, SED, CDE, CEB, GED, TED or CEO.'
)

_CED_ASSISTANT_TAGLINE = "Tu asistente de IA. Marketing. Ventas. Prospección."
CED_ASSISTANT_TAGLINE = _CED_ASSISTANT_TAGLINE
_CED_ON_IMAGE_SPELLING_LOCK = (
    "LOCKED SPELLING on this image — copy character-by-character: "
    '"IA" (never I4, 14, lA); '
    '"Prospección" (never Prosaeccion, Prosaección, Prosaecion); '
    '"CED" as C-E-D (never SEC, SED, CDE, CEB, GED, TED, CEO); '
    '"Marketing"; "Ventas".'
)
_CED_WORDMARK_LOCK = (
    "LOCKED WORDMARK: if any brand letters appear they must read exactly CED "
    "(Latin letters C then E then D). Never render SEC, SED, CDE, CEB, GED, TED, "
    "or CEO. Do not reverse or scramble those three letters."
)
# Solo correcciones de tipografía (I4 / Prosaeccion). NO «prospección» ni
# «asistente de IA» sueltos: esos aparecen en listados de capacidades CED.
_FIX_ON_IMAGE_SPELLING = re.compile(
    r"(?is)"
    r"(?:"
    r"\bi4\b|"
    r"prosaec|"
    r"(?:corrige(?:r)?|arregla(?:r)?|mejora(?:r)?|cambia(?:r)?)\s+"
    r"(?:la\s+|el\s+|los\s+|las\s+)?"
    r"(?:ia|ortograf|texto|letras?|prospecci)|"
    r"dijo\s+i4|"
    r"en\s+vez\s+de\s+i4"
    r")"
)
_IMAGE_SPELLING_FIXES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bI4\b", re.I), "IA"),
    (re.compile(r"\bprosaec+c?i[oó]n\b", re.I), "Prospección"),
    (re.compile(r"\bprospeccion\b", re.I), "Prospección"),
)
_HARD_NO_TEXT_RULE = (
    "CRITICAL: photorealistic or illustrated SCENE ONLY. "
    "Zero letters, words, titles, captions, subtitles, watermarks, logos as text, "
    "UI labels, or typography of any kind. Do NOT write the brief or the user's "
    "request onto the image."
)
_DECORATIVE_UI_RULE = (
    "Include complex UI/UX data elements, abstract micro-text, digital metrics, "
    "and sci-fi glyphs. The text must look like a functional, illegible technical "
    "interface, NOT a marketing headline. Do not render logos, watermarks, "
    "user prompts, or commands such as 'genera una imagen' on the screens."
)
_DECORATIVE_UI_MARKER = "functional, illegible technical interface"

ImageTextMode = Literal["none", "decorative", "literal"]

# Compuestos — «pantalla» o «código» sueltos no disparan HUD (baño con TV, código de descuento).
_DECORATIVE_UI_SIGNAL = re.compile(
    r"(?is)\b("
    r"hologr(?:ama|áfic[oa]|afic[oa]|aphic)?|"
    r"\bhud\b|"
    r"interfaz\s+(?:hologr|digital|futurista|de\s+ced|sci|c[ií]an)|"
    r"dashboard|"
    r"pantalla\s+(?:de\s+)?(?:datos|c[oó]digo|hologr|sci|futurista)|"
    r"c[oó]digo\s+en\s+pantalla|"
    r"sci-?fi\s+ui|"
    r"panel\s+de\s+control|"
    r"jarvis"
    r")\b"
)
_ORGANIC_PHOTO_SIGNAL = re.compile(
    r"(?is)\b("
    r"águila|aguila|ba[nñ]o|playa|monta[nñ]as?|atardecer|retrato|paisaje|"
    r"espejo|bosque|oc[eé]ano|cielo\s+lluvioso|naturaleza"
    r")\b"
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


def wants_ced_tagline_lock(text: str) -> bool:
    """True si el usuario pide corregir IA/I4 o Prospección en la imagen (no un brief genérico)."""
    return bool(_FIX_ON_IMAGE_SPELLING.search(text or ""))


def _looks_like_ced_tagline(text: str) -> bool:
    t = (text or "").casefold()
    if "asistente" not in t:
        return False
    if not re.search(r"(?i)\bia\b|\bi4\b", t):
        return False
    return bool(
        re.search(r"(?i)marketing", t)
        and re.search(r"(?i)(?:ventas|prospecci|prosaec)", t)
    )


def lock_on_image_spelling(text: str) -> str:
    """Corrige fallos típicos de tipografía en imagen (I4→IA, Prosaeccion→Prospección)."""
    t = unicodedata.normalize("NFC", text or "")
    if not t:
        return t
    for pattern, right in _IMAGE_SPELLING_FIXES:
        t = pattern.sub(right, t)
    t = _apply_typo_fixes(t)
    if len(t.strip()) <= 8 and re.fullmatch(r"(?i)sec|sed|cde|ceb|ged|ted", t.strip()):
        return "CED"
    if len(t) <= 120 and _looks_like_ced_tagline(t):
        return _CED_ASSISTANT_TAGLINE
    return t


_CED_WORDMARK_REQUEST = re.compile(
    r"(?is)\b(?:logo|wordmark|isotipo|emblema|escudo|sello|letrero|marca)\b.{0,48}\bced\b"
    r"|\bced\b.{0,48}\b(?:logo|wordmark|isotipo|emblema|escudo|sello|letrero)\b"
)


def user_requests_ced_wordmark(text: str) -> bool:
    """True si piden el logo/nombre CED escrito en la imagen."""
    return bool(_CED_WORDMARK_REQUEST.search(text or ""))


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
    r"detalles?\s+(?:resumidos\s+)?escritos?|textos?\s+(?:exactos?|literales?|visibles?|legibles?)|"
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
    r"quiero\s+que\s+mantengas\s+(?:l[ao]s?\s+)?textos?|"
    # Agregar / poner texto sobre imagen ya existente (caso reportado)
    r"agr[eé]ga(?:r|le|me|nos)?\s+(?:un\s+|el\s+)?texto|"
    r"a[nñ]ade(?:r|le|me|nos)?\s+(?:un\s+|el\s+)?texto|"
    r"pon(?:le|me|ga|gan)?\s+(?:un\s+|el\s+)?texto|"
    r"suma(?:r|le|me)?\s+(?:un\s+|el\s+)?texto|"
    r"incluye(?:r|le|me)?\s+(?:un\s+|el\s+)?texto|"
    r"texto\s+(?:que\s+)?(?:resalte|destaque|muestre|hable\s+de)|"
    r"resalt(?:a|e|ar)\s+(?:el\s+)?(?:dolor|cansancio|problema)|"
    r"dolor\s*[→\-–]+\s*soluci[oó]n|dolor\s+y\s+(?:la\s+)?soluci[oó]n|"
    # «EN TEXTO» / «donde pongas las características…»
    r"\ben\s+texto\b|\bcon\s+texto\b|"
    r"donde\s+pongas?|"
    r"pon(?:le|ga|gan|me)?\s+las?\s+(?:siguientes\s+)?"
    r"(?:caracter[ií]sticas|etiquetas|textos?|nombres?)|"
    # Letreros / carteles / nombres visibles (señal fuerte + verbo de texto)
    r"(?:letrero|cartel|r[oó]tulo|placa|banner)\s+"
    r"(?:con|que\s+(?:diga|ponga|muestre|aparezca)|donde\s+diga)|"
    r"con\s+el\s+nombre\s+(?:de\s+)?"
    r")\b",
    re.I,
)

# Formatos que SIEMPRE llevan tipografía. Nano Banana 2 falla en ortografía
# (p.ej. «equipo» → «eqipo»); estos van al híbrido GPT Image / Ideogram.
_GRAPHIC_COPY_FORMAT = re.compile(
    r"(?i)\b(?:flyer|cartel|letrero|r[oó]tulo|infograf[ií]a|banner)\b"
)
_NO_TEXT_GUARD_HINT = re.compile(
    r"(?i)\b(?:zero letters|scene only|sin texto|ninguna letra)\b"
)


def prompt_requires_precise_text(prompt: str) -> bool:
    """Texto crítico en la imagen → GPT Image (fallback Ideogram), no Nano Banana.

    Mira solo el pedido ACTUAL (nunca historial). Incluye comillas / «que diga»
    y formatos gráficos que siempre llevan copy (flyer, banner, cartel…).
    «Sin texto» gana: escena pura se queda en Nano Banana.
    """
    t = (prompt or "").strip()
    if not t:
        return False
    from app.services.chat_intents import is_script_narrative_request

    if is_script_narrative_request(t):
        return False
    if _SCENE_FORBIDS_TEXT.search(t):
        return False
    if extract_quoted_phrases(t):
        return True
    if _IDEOGRAM_EXPLICIT_TEXT_REQUEST.search(t):
        return True
    if wants_ced_tagline_lock(t):
        return True
    if user_requests_ced_wordmark(t):
        return True
    return bool(_GRAPHIC_COPY_FORMAT.search(t))


def resolve_image_text_mode(text: str) -> ImageTextMode:
    """LITERAL > DECORATIVE > NONE. Clasifica el brief fusionado, no solo el último comando."""
    t = (text or "").strip()
    if not t:
        return "none"
    if _SCENE_FORBIDS_TEXT.search(t):
        return "none"
    if prompt_requires_precise_text(t) or extract_quoted_phrases(t):
        return "literal"
    if _DECORATIVE_UI_SIGNAL.search(t):
        if _ORGANIC_PHOTO_SIGNAL.search(t) and not user_requests_ced_branding(t):
            # «baño con pantalla» / águila: foto, no HUD, salvo que el sujeto sea CED.
            return "none"
        return "decorative"
    return "none"


def image_text_mode_allows_ui(mode: ImageTextMode, text: str) -> bool:
    """LITERAL + señales HUD (carrusel CED con overlay + holograma)."""
    if mode == "decorative":
        return True
    if mode == "literal" and _DECORATIVE_UI_SIGNAL.search(text or ""):
        return True
    return False


def ensure_image_quality_guards(prompt: str, *, wants_text: bool | None = None) -> str:
    """Añade encuadre seguro y, si hay tipografía, reglas de ortografía (idempotente)."""
    t = (prompt or "").strip()
    if not t:
        return t
    no_text = (
        "No text, letters" in t
        or _HARD_NO_TEXT_RULE[:40] in t
        or _NO_TEXT_GUARD_HINT.search(t)
    )
    if wants_text is None:
        wants_text = (not no_text) and (
            "TEXTOS EXACTOS" in t
            or "Include the requested labels" in t
            or "Ortografía española" in t
            or "SPELLING:" in t
            or prompt_requires_precise_text(t)
        )
    extras: list[str] = []
    if "FULL FRAME" not in t and "SAFE AREA" not in t:
        extras.append(_FRAME_SAFE_RULE)
    if wants_text:
        if "Ortografía española" not in t:
            extras.append(_ORTHOGRAPHY_RULE)
        if "SPELLING:" not in t:
            extras.append(_SPELLING_STRICT_RULE)
    if not extras:
        return t
    return f"{t} {' '.join(extras)}".strip()[:4000]


def prompt_requires_ideogram_text(prompt: str) -> bool:
    """Alias histórico — mismo detector que `prompt_requires_precise_text`."""
    return prompt_requires_precise_text(prompt)


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
    """True solo si el usuario pidió tipografía visible — nunca por «Sin texto…»."""
    prompt_s = (prompt or "").strip()
    ctx_s = (context or "").strip()
    blob = f"{prompt_s} {ctx_s}"
    if "TEXTOS EXACTOS" in blob:
        return True
    # Brief de escena pura: la palabra «texto» en «Sin texto» NO debe activar tipografía.
    if _SCENE_FORBIDS_TEXT.search(prompt_s) and "TEXTOS EXACTOS" not in prompt_s:
        if not extract_quoted_phrases(prompt_s) and not prompt_requires_ideogram_text(prompt_s):
            return False
    if extract_quoted_phrases(blob):
        return True
    if prompt_requires_ideogram_text(prompt_s):
        return True
    if _TITLE_DESC_LINE.search(blob):
        return True
    if _IMAGE_TEXT_HINT.search(blob):
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
        label = lock_on_image_spelling(sanitize_label(raw))
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
        locked_tagline = label.casefold() == _CED_ASSISTANT_TAGLINE.casefold()
        cap = 80 if locked_tagline else max_chars
        if len(label) > cap:
            label = label[: cap - 1].rsplit(" ", 1)[0].strip()
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
    """Expande el sujeto del usuario como escena — sin tipografía ni marca CED."""
    subject = (visual or "").strip(" ,.;")
    if has_reference:
        if subject:
            return (
                f"Photographic edit of the reference image: {subject}. "
                "Keep style and composition; high quality, coherent lighting. "
                f"{_HARD_NO_TEXT_RULE}"
            )
        return (
            "Faithful variation of the reference image per the user request; "
            f"high quality, do not change the subject to another brand. {_HARD_NO_TEXT_RULE}"
        )
    if subject:
        return (
            f"Photorealistic scene depicting: {subject}. "
            "Clear composition, natural lighting, sharp detail, professional result "
            f"faithful to that subject only. {_HARD_NO_TEXT_RULE}"
        )
    return (
        "High-quality image faithful to the user's requested subject, clear composition, "
        f"good lighting, no unrelated brands or themes. {_HARD_NO_TEXT_RULE}"
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


def build_direct_image_prompt(
    user_text: str,
    *,
    has_reference: bool = False,
    context: str = "",
    visual_override: str = "",
) -> dict[str, Any]:
    """Adaptador mínimo: pedido del usuario en lenguaje natural → modelo de imagen.

    Alineado con la guía de Google para Gemini Flash Image / Nano Banana: el modelo
    entiende mejor la descripción directa. Sin reescritura de escena, sin historial
    (el contexto mezclaba temas de turnos previos) y sin «TEXTOS EXACTOS» inventados
    a partir del brief.

    ``visual_override``: escena enriquecida por el expander (luz/composición). La
    política de texto (NONE / DECORATIVE / LITERAL) sale siempre del ancla.
    """
    _ = context  # historial crudo ignorado a propósito
    from app.services.gemini_images import (
        strip_image_generation_instruction,
        strip_image_prompt_meta,
    )

    raw = (user_text or "").strip()
    cleaned = re.sub(
        r"(?is)^(ok(?:ay)?|vale|listo|perfecto|bueno|bien)[\s,.:\-]+",
        "",
        raw,
    ).strip()
    scene = strip_image_prompt_meta(strip_image_generation_instruction(cleaned)).strip()
    if not scene:
        scene = cleaned or raw
    override = strip_image_prompt_meta((visual_override or "").strip())
    if override:
        scene = override

    quoted = extract_quoted_phrases(raw)
    mode = resolve_image_text_mode(raw)
    wants_wordmark = user_requests_ced_wordmark(raw)
    wants_text = mode == "literal" or wants_wordmark
    wants_ced = user_requests_ced_branding(raw)
    allow_ui = image_text_mode_allows_ui(mode, raw)
    quoted = [lock_on_image_spelling(q) for q in quoted]
    if wants_wordmark and "CED" not in quoted:
        quoted = ["CED", *[q for q in quoted if q.upper() != "CED"]]
    lock_tagline = wants_ced_tagline_lock(raw)
    if wants_text and lock_tagline:
        if _CED_ASSISTANT_TAGLINE not in quoted:
            quoted = [_CED_ASSISTANT_TAGLINE, *[q for q in quoted if q != _CED_ASSISTANT_TAGLINE]]

    parts: list[str] = [scene]
    if has_reference:
        parts.append("Use the attached image only as style/composition reference.")
    if wants_ced:
        parts.append(
            "Style with CED brand identity when relevant (futuristic cyan/blue HUD, "
            "dark developer atmosphere, premium UI glow)."
        )
    parts.append(_FRAME_SAFE_RULE)
    if wants_text:
        parts.append(
            "Include the requested labels as clear legible on-image text. "
            "Every word must be complete and correctly spelled. "
            "Do NOT write meta commands such as 'genera una imagen', 'okay ahora', "
            "or system instructions onto the image."
        )
        parts.append(_ORTHOGRAPHY_RULE)
        parts.append(_SPELLING_STRICT_RULE)
        if wants_ced or lock_tagline or wants_wordmark:
            parts.append(_CED_ON_IMAGE_SPELLING_LOCK)
        if wants_wordmark:
            parts.append(_CED_WORDMARK_LOCK)
        if quoted:
            parts.append(format_verbatim_image_copy(quoted))
        if allow_ui:
            parts.append(_DECORATIVE_UI_RULE)
    elif allow_ui:
        parts.append(_DECORATIVE_UI_RULE)
    else:
        parts.append(
            "No text, letters, titles, captions, subtitles, or watermarks anywhere "
            "in the image."
        )

    prompt = " ".join(p for p in parts if p).strip()[:3800]
    return {
        "visual_brief": scene,
        "overlay_lines": [],
        "wants_literal_text": wants_text,
        "text_mode": mode,
        "technical_prompt": prompt,
        "prompt": prompt,
    }


def orchestrate_image_generation_brief(
    user_text: str,
    *,
    context: str = "",
    has_reference: bool = False,
) -> dict[str, Any]:
    """Compat: delega al adaptador directo (sin orquestación pesada)."""
    return build_direct_image_prompt(
        user_text,
        has_reference=has_reference,
        context=context,
    )


def compose_persuasive_overlay_lines(user_text: str, *, max_lines: int = 2) -> list[str]:
    """Redacta 1–2 líneas cortas (PAS / dolor→solución) cuando el usuario pide texto
    persuasivo sin comillas literales.

    No inventa claims de producto; usa el dolor/solución que el usuario ya nombró.
    """
    t = (user_text or "").strip()
    if not t:
        return []

    quoted = [normalize_spanish(q) for q in extract_quoted_phrases(t) if q.strip()]
    if quoted:
        return quoted[:max_lines]

    low = t.lower()
    pain = ""
    if re.search(r"\bcansancio\b", low):
        pain = "¿Cansancio diario otra vez?"
    elif re.search(r"\bfatiga\b", low):
        pain = "¿Fatiga que no se va?"
    elif re.search(r"\bagotad[oa]\b", low):
        pain = "¿Agotada sin explicación?"
    elif re.search(r"\bdolor\b", low):
        pain = "Ese dolor no tiene por qué mandar."
    elif re.search(r"\bestr[eé]s\b", low):
        pain = "¿Estrés que te frena cada día?"
    elif re.search(r"\bproblema\b", low):
        pain = "Hay un problema real aquí."

    wants_solution = bool(
        re.search(r"\bsoluci[oó]n(?:es)?\b|\bbeneficio|\bresultado|\bsalida\b", low)
    )
    solution = ""
    if wants_solution:
        if "cansancio" in low or "fatiga" in low or "agotad" in low:
            solution = "Hay una solución más simple."
        elif "dolor" in low:
            solution = "La solución empieza hoy."
        else:
            solution = "Y sí: hay una solución."

    lines: list[str] = []
    if pain:
        lines.append(pain)
    if solution and solution not in lines:
        lines.append(solution)
    if not lines and prompt_requires_precise_text(t):
        # Pedido genérico de texto persuasivo sin keyword clara.
        lines = ["Hay un problema real aquí.", "Y también hay una solución."]
    return [normalize_spanish(x) for x in lines[:max_lines] if x]


_BG_CHANGE_RE = re.compile(
    r"(?is)\b(?:"
    r"cambia(?:r)?\s+(?:el\s+)?fondo|"
    r"otro\s+fondo|"
    r"nuevo\s+fondo|"
    r"fondo\s+(?:a|de|en)\s+\w+|"
    r"pon(?:le|me)?\s+(?:un\s+)?fondo|"
    r"background|"
    r"change\s+(?:the\s+)?background"
    r")\b"
)


def user_requests_background_change(text: str) -> bool:
    """True si el usuario pide cambiar el fondo (no solo tipografía)."""
    return bool(_BG_CHANGE_RE.search(text or ""))


def build_reference_text_edit_prompt(
    user_text: str,
    *,
    overlay_lines: list[str] | None = None,
) -> str:
    """Prompt para editar imagen existente: conservar sujeto + tipografía PAS."""
    lines = [lock_on_image_spelling(ln) for line in (overlay_lines or []) if (ln := line.strip())]
    if wants_ced_tagline_lock(user_text):
        lines = [_CED_ASSISTANT_TAGLINE]
    elif not lines:
        lines = compose_persuasive_overlay_lines(user_text)
    verbatim = format_verbatim_image_copy(lines) if lines else ""
    change_bg = user_requests_background_change(user_text)
    if change_bg:
        keep = (
            "Edit the attached photo. Keep the SAME person, face, clothing and pose. "
            "CHANGE the background as the user requested. "
            "Do NOT replace the subject with a different person "
            "unless the user explicitly asked for that."
        )
    else:
        keep = (
            "Edit the attached photo. Keep the SAME person, face, clothing, pose, "
            "lighting and background. Do NOT replace the subject with a different person "
            "or a different gesture unless the user explicitly asked for that."
        )
    parts = [
        keep,
        "Add clear, legible Spanish on-image typography for a marketing ad "
        "(pain → solution / PAS). Short lines only. High contrast. No watermarks. "
        f"{_FRAME_SAFE_RULE} {_ORTHOGRAPHY_RULE} {_SPELLING_STRICT_RULE}",
        f"User request: {strip_image_generation_instruction_safe(user_text)}",
    ]
    if verbatim:
        parts.append(verbatim)
        parts.append(_CED_ON_IMAGE_SPELLING_LOCK)
    else:
        parts.append(
            "Include the persuasive text the user asked for as visible labels on the image."
        )
    return " ".join(p for p in parts if p).strip()[:3800]


def strip_image_generation_instruction_safe(text: str) -> str:
    try:
        from app.services.gemini_images import strip_image_generation_instruction

        return strip_image_generation_instruction(text or "") or (text or "").strip()
    except Exception:  # noqa: BLE001
        return (text or "").strip()


def format_verbatim_image_copy(lines: list[str], *, headline: str | None = None) -> str:
    """Bloque de instrucción con textos literales para modelos de imagen."""
    all_lines = [lock_on_image_spelling(normalize_spanish(line)) for line in lines if line.strip()]
    if headline:
        head = normalize_spanish(headline)
        if head and head not in all_lines:
            all_lines.insert(0, head)
    if not all_lines:
        return ""
    quoted = [f'"{line}"' for line in all_lines]
    return (
        "TEXTOS EXACTOS EN ESPAÑOL (ortografía obligatoria — copiar CARÁCTER POR CARÁCTER; "
        "no parafrasear, no inventar palabras, no mezclar inglés, no omitir letras):\n"
        + "\n".join(f"- {q}" for q in quoted)
        + "\nKeep every word fully inside the frame, centered, never cropped. "
        "Si no puedes renderizar texto perfecto, usa MENOS texto pero sin errores ortográficos."
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
        "TEXTOS EXACTOS EN LA IMAGEN (una línea cada uno; copiar tal cual, sin faltas):\n"
        + "\n".join(f"- {q}" for q in quoted)
        + f"\n{_FRAME_SAFE_RULE} {_SPELLING_STRICT_RULE} "
        "Si no puedes escribir perfecto, usa solo el titular y 2 viñetas cortas."
    )


def augment_image_prompt(prompt: str, context: str = "") -> str:
    """Capa de brief visual: anti-fuga + textos literales SOLO si el pedido los exige."""
    base = strip_prompt_meta_for_image((prompt or "").strip())
    if not base:
        return base
    ctx = strip_prompt_meta_for_image(context or "")

    # Escena ya marcada «sin texto» / orquestada: NUNCA añadir TEXTOS EXACTOS ni
    # usar el brief como titular (bug: pintaba «un hombre recostado…» en la foto).
    if "TEXTOS EXACTOS" not in base and (
        _SCENE_FORBIDS_TEXT.search(base) or _HARD_NO_TEXT_RULE[:40] in base
    ):
        if not prompt_requires_ideogram_text(base) and not extract_quoted_phrases(base):
            if _HARD_NO_TEXT_RULE[:40] not in base:
                return ensure_image_quality_guards(
                    f"{base.rstrip('. ')}. {_HARD_NO_TEXT_RULE}",
                    wants_text=False,
                )
            return ensure_image_quality_guards(base, wants_text=False)

    if "TEXTOS EXACTOS" in base:
        if _ORTHOGRAPHY_RULE.split(".")[0] not in base:
            return ensure_image_quality_guards(
                f"{base} {_ORTHOGRAPHY_RULE} {_CREATIVE_NO_LEAK}",
                wants_text=True,
            )
        if "PROHIBIDO escribir" not in base and "PROHIBIDO renderizar" not in base:
            return ensure_image_quality_guards(
                f"{base} {_CREATIVE_NO_LEAK}",
                wants_text=True,
            )
        return ensure_image_quality_guards(base, wants_text=True)

    overlay = collect_image_overlay_lines(base, ctx)
    # Solo titular desde overlays reales — NUNCA base[:60] (era el prompt pintado).
    headline = ""
    if overlay:
        headline = build_image_headline(ctx, overlay[0])

    if overlay or image_prompt_needs_verbatim_text(base, ctx):
        verbatim = format_verbatim_image_copy(overlay, headline=headline or None)
        if verbatim:
            return ensure_image_quality_guards(
                f"{base} {_ORTHOGRAPHY_RULE} {verbatim} {_CREATIVE_NO_LEAK} "
                "Prefiere tipografía grande y clara; máximo una frase corta (≤12 palabras) "
                "si el texto es largo. Mejor poco texto correcto que un párrafo ilegible.",
                wants_text=True,
            )
        # Pedido de tipografía sin líneas concretas: conservar/mejorar textos de la
        # referencia; NUNCA pintar el pedido del usuario como tipografía.
        return ensure_image_quality_guards(
            f"{base} {_ORTHOGRAPHY_RULE} {_CREATIVE_NO_LEAK} "
            "Incluye tipografía legible en español. Si hay imagen de referencia con "
            "etiquetas o títulos, reprodúcelos con ortografía correcta. "
            "No escribas en la imagen el pedido del usuario ni frases meta.",
            wants_text=True,
        )

    # Escena pura: anti-texto duro; no mencionar «pedido/usuario» (el modelo lo pinta).
    return ensure_image_quality_guards(
        f"{base.rstrip('. ')}. {_HARD_NO_TEXT_RULE}",
        wants_text=False,
    )

IMAGE_EMBEDDED_TEXT_DISCLAIMER = (
    "Señor, aviso: el texto dentro de imágenes generadas por IA "
    "suele no salir perfectamente legible. Aquí está el resultado:"
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
