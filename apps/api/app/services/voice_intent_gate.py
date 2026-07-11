"""Clasificación local rápida de intención de voz — sin LLM externo.

Determina si un turno menciona explícitamente un módulo/herramienta CED.
Si no hay señal clara, el router salta orquestador + Gemini y va directo a Llama.
"""

from __future__ import annotations

import re

# Señales locales por dominio — regex only, sin red.
_MODULE_SIGNAL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "camera",
        re.compile(
            r"\b("
            r"c[aá]mara|camara|visi[oó]n|video|"
            r"activa(?:r)?\s+(?:la\s+)?c[aá]mara|"
            r"qu[eé]\s+ves|qu[eé]\s+me\s+muestro|"
            r"analiza(?:r)?\s+(?:esto|lo\s+que|la\s+c[aá]mara)|"
            r"busca(?:r)?\s+lo\s+visible|"
            r"describ(?:e|ir)\s+lo\s+que"
            r")\b",
            re.I,
        ),
    ),
    (
        "publish",
        re.compile(
            r"\b("
            r"publica(?:r)?|postea(?:r)?|"
            r"instagram|facebook|"
            r"sube(?:r)?\s+a\s+(?:instagram|facebook|redes)|"
            r"comparte(?:r)?\s+en\s+(?:instagram|facebook|redes)"
            r")\b",
            re.I,
        ),
    ),
    (
        "prospection",
        re.compile(
            r"\b("
            r"prospecci[oó]n|prospectos?|"
            r"comentarios?\s+(?:de\s+)?(?:instagram|facebook|redes)|"
            r"leer\s+comentarios?|"
            r"clientes?\s+(?:potenciales?|calientes?)|"
            r"modo\s+(?:prospecci[oó]n|ventas|ascenso)"
            r")\b",
            re.I,
        ),
    ),
    (
        "image_gen",
        re.compile(
            r"\b("
            r"genera(?:r|me)?|crea(?:r|me)?|dise[nñ]a(?:r|me)?|"
            r"dibuja(?:r|me)?|pinta(?:r|me)?|"
            r"imagen(?:es)?|foto(?:s)?|ilustraci[oó]n|logo|banner|flyer|portada|"
            r"edita(?:r|me)?\s+(?:la\s+)?(?:imagen|foto)"
            r")\b",
            re.I,
        ),
    ),
    (
        "pdf",
        re.compile(
            r"\b("
            r"pdf|documento|reporte|"
            r"genera(?:r|me)?\s+(?:un\s+)?pdf|"
            r"crea(?:r|me)?\s+(?:un\s+)?pdf|"
            r"haz(?:me)?\s+un\s+pdf|exporta(?:r)?\s+(?:a\s+)?pdf"
            r")\b",
            re.I,
        ),
    ),
    (
        "map",
        re.compile(
            r"\b("
            r"mapa|navega(?:r|ción|ciona)?|gps|conducir|modo\s+conducir|"
            r"ll[eé]vame\s+a|c[oó]mo\s+llego|"
            r"traza(?:r)?\s+(?:la\s+)?ruta|"
            r"abre(?:r)?\s+(?:el\s+)?mapa|"
            r"busca(?:r)?\s+cerca|d[oó]nde\s+hay"
            r")\b",
            re.I,
        ),
    ),
    (
        "calendar",
        re.compile(
            r"\b("
            r"calendario|agenda(?:r|me)?|cita(?:s)?|evento(?:s)?|"
            r"reuni[oó]n|"
            r"qu[eé]\s+tengo\s+(?:ma[nñ]ana|hoy|esta\s+semana)|"
            r"programa(?:r|me)\s+(?:una\s+)?(?:cita|reuni[oó]n)"
            r")\b",
            re.I,
        ),
    ),
    (
        "gmail",
        re.compile(
            r"\b("
            r"gmail|correo(?:s)?|email(?:s)?|bandeja|"
            r"l[eé]e(?:me)?\s+(?:el\s+|los\s+|mis\s+)?(?:correo|email|gmail)|"
            r"env[ií]a(?:r|me)?\s+(?:un\s+)?(?:correo|email)|"
            r"ultimo\s+gmail|último\s+correo"
            r")\b",
            re.I,
        ),
    ),
    (
        "finance",
        re.compile(
            r"\b("
            r"finanzas?|gasto(?:s)?|ingreso(?:s)?|"
            r"pagu[eé]|gast[eé]|compr[eé]|cobr[eé]|"
            r"plan\s+de\s+ahorro|presupuesto|"
            r"mis\s+finanzas|modo\s+financiero|"
            r"cu[aá]nto\s+(?:he\s+)?gast|cu[aá]nto\s+debo|"
            r"pagos?\s+pendientes?"
            r")\b",
            re.I,
        ),
    ),
    (
        "environment",
        re.compile(
            r"\b("
            r"clima|tiempo|temperatura|lluvia|llover|"
            r"calidad\s+del\s+aire|polen|alergia|"
            r"qu[eé]\s+clima|c[oó]mo\s+est[aá]\s+el\s+tiempo"
            r")\b",
            re.I,
        ),
    ),
    (
        "web_search",
        re.compile(
            r"\b("
            r"noticias|busca(?:r)?\s+(?:en\s+)?internet|"
            r"busca(?:r)?\s+informaci[oó]n|"
            r"precio\s+de|cu[aá]nto\s+cuesta"
            r")\b",
            re.I,
        ),
    ),
    (
        "memory",
        re.compile(
            r"\b("
            r"recuerda(?:\s+que)?|guarda(?:\s+esto)?|memoriza|"
            r"crm|contacto|cliente\s+nuevo"
            r")\b",
            re.I,
        ),
    ),
    (
        "advanced",
        re.compile(
            r"\b("
            r"modo\s+avanzado|an[aá]lisis\s+avanzado|"
            r"consulta(?:r)?\s+claude|claude|"
            r"sistema\s+avanzado|an[aá]lisis\s+profundo"
            r")\b",
            re.I,
        ),
    ),
)


def _normalize(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def has_explicit_module_signal(user_text: str) -> bool:
    """True si el texto menciona explícitamente algún módulo/herramienta."""
    norm = _normalize(user_text)
    if not norm:
        return False
    return any(pattern.search(norm) for _, pattern in _MODULE_SIGNAL_PATTERNS)


def detect_local_module_hints(user_text: str) -> list[str]:
    """Devuelve nombres de módulo cuya señal local coincide (puede ser >1)."""
    norm = _normalize(user_text)
    if not norm:
        return []
    hits: list[str] = []
    for name, pattern in _MODULE_SIGNAL_PATTERNS:
        if pattern.search(norm):
            hits.append(name)
    return hits


def should_run_orchestrator(
    user_text: str,
    *,
    active_module: str | None = None,
    forced_module: str | None = None,
) -> bool:
    """Decide si el turno debe pasar por orquestador + detector completo."""
    if active_module:
        return True
    if forced_module:
        return True
    return has_explicit_module_signal(user_text)
