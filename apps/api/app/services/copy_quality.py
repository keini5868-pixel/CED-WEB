"""Normalización y textos literales para redacción en español (chat e imágenes)."""

from __future__ import annotations

import re
import unicodedata

# Correcciones frecuentes (usuario, voz, o modelos de imagen).
_TYPO_MAP: dict[str, str] = {
    "veneficio": "beneficio",
    "veneficios": "beneficios",
    "caracteristicas": "características",
    "especificaciones": "especificaciones",
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

_ENGLISH_IN_SPANISH = re.compile(
    r"\b(immune|digestion|nutrition|energy|health)\b",
    re.I,
)
_ENGLISH_REPLACEMENTS = {
    "immune": "inmune",
    "digestion": "digestión",
    "nutrition": "nutrición",
    "energy": "energía",
    "health": "salud",
}


def normalize_spanish(text: str) -> str:
    """Corrige typos comunes y normaliza espacios."""
    t = unicodedata.normalize("NFC", (text or "").strip())
    if not t:
        return t
    t = re.sub(r"\s+", " ", t)
    for eng, spa in _ENGLISH_REPLACEMENTS.items():
        t = re.sub(rf"\b{eng}\b", spa, t, flags=re.I)
    lower = t.lower()
    for wrong, right in _TYPO_MAP.items():
        lower = re.sub(rf"\b{re.escape(wrong)}\b", right, lower, flags=re.I)
    # Restaurar capitalización de oración si el original empezaba en mayúscula.
    if text[:1].isupper() and lower:
        lower = lower[0].upper() + lower[1:]
    return lower


def sanitize_benefit_title(title: str) -> str:
    clean = normalize_spanish(title.strip())
    clean = re.sub(r"\s+", " ", clean)
    if not clean:
        return clean
    return clean[0].upper() + clean[1:]


def _first_phrase(desc: str, *, max_chars: int = 48) -> str:
    text = normalize_spanish(desc)
    text = re.split(r"[.;]\s", text, maxsplit=1)[0].strip()
    if len(text) > max_chars:
        text = text[: max_chars - 1].rsplit(" ", 1)[0].strip()
    return text


def compact_overlay_line(title: str, desc: str) -> str:
    """Línea corta para gráfico — menos texto = menos errores del modelo de imagen."""
    label = sanitize_benefit_title(title)
    phrase = _first_phrase(desc, max_chars=44)
    if not phrase:
        return label
    if len(f"{label}: {phrase}") > 58:
        return label
    return f"{label}: {phrase}"


def overlay_lines_from_benefit_strings(bullets: list[str]) -> list[str]:
    lines: list[str] = []
    for bullet in bullets:
        if ":" in bullet:
            title, _, desc = bullet.partition(":")
            line = compact_overlay_line(title, desc)
        else:
            line = sanitize_benefit_title(bullet)
        line = normalize_spanish(line)
        if line and line not in lines:
            lines.append(line)
        if len(lines) >= 5:
            break
    return lines


def build_flyer_headline(subject: str = "") -> str:
    _ = subject
    return normalize_spanish("Nutrición y digestión óptima")


def format_verbatim_image_copy(lines: list[str], *, headline: str | None = None) -> str:
    """Bloque de instrucción con textos literales para modelos de imagen."""
    all_lines = [normalize_spanish(line) for line in lines if line.strip()]
    if headline:
        all_lines.insert(0, normalize_spanish(headline))
    if not all_lines:
        return ""
    quoted = [f'"{line}"' for line in all_lines]
    return (
        "TEXTOS EXACTOS EN ESPAÑOL (ortografía obligatoria — copiar CARÁCTER POR CARÁCTER; "
        "no parafrasear, no inventar palabras, no mezclar inglés):\n"
        + "\n".join(f"- {q}" for q in quoted)
        + "\nSi no puedes renderizar texto perfecto, usa MENOS texto pero sin errores ortográficos."
    )


def polish_spanish_for_user(text: str) -> str:
    """Pulido ligero para respuestas visibles al usuario."""
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
