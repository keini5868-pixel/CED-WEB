"""Conocimiento curado PM International / FitLine para chat y modo avanzado.

Fuente única: plugin Oportunidades `fitline_pm` (sin inventar productos ni precios).
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

from app.services.opportunities_pilot.catalog import get_plugin
from app.services.opportunities_pilot.plugins.fitline_pm import OPPORTUNITY_ID
from app.services.opportunities_pilot.synthesize import SECTION_ORDER

# Marcas / empresa
_BRAND = re.compile(
    r"\b(?:"
    r"fit\s*-?\s*line|fitline|"
    r"pm[\s\-]?international|pm\s*international|"
    r"pme\s*business|pmebusiness|"
    r"pm[\s\-]?income\s*plan"
    r")\b",
    re.I,
)

# Productos / SKUs distintivos (incluye typo Activise ↔ Activize)
_DISTINCT_PRODUCTS = re.compile(
    r"\b(?:"
    r"activize|activise|oxyplus|"
    r"restorate|"
    r"power\s*-?\s*cocktail|powercocktail|"
    r"munogen|proshape|topshape|"
    r"microsolve|herbaslim|"
    r"optimal[\s\-]?set|"
    r"generation\s*50\+|"
    r"women\+|men\+|"
    r"antioxy|ib\s*5|ib⁵|"
    r"ultimate\s+young|hydrating[\s\-]?shot"
    r")\b",
    re.I,
)

# «Basics» es genérico en inglés — solo con marca o producto FitLine cerca
_BASICS = re.compile(r"\bbasics\b", re.I)

_PROMPT_RULES = (
    "Usa SOLO estos datos validados del módulo Oportunidades. "
    "NO inventes productos, precios, comisiones, claims de salud ni cifras. "
    "Si el dato no está aquí, dilo con honestidad y remite a fuentes oficiales "
    "(fitline.com / pm-international.com / Partner Area). "
    "NO preguntes qué es un producto o marca que ya aparece en este contexto: "
    "aplícalo directamente al pedido del usuario "
    "(ideas de venta, copy, prompts, conceptos creativos, estrategia, etc.). "
    "Si pide CONTENIDO / IDEA / COPY / PROMPT / GUION de texto sobre FitLine o "
    "un producto de este catálogo: ENTREGA el texto completo YA, usando este "
    "conocimiento. NO generes imagen. NO digas «no tengo info» si el producto "
    "está aquí. NO abras con preguntas básicas (qué es, para qué sirve, a quién "
    "va dirigido) — ya lo sabes por este bloque."
)

_FITLINE_CONTENT_DELIVERY_RULES = (
    "ENTREGA FITLINE/PM (texto): responde con contenido útil y listo para usar "
    "(idea, copy, prompt delimitado con ---, guion o caption). "
    "Sé concreto y accionable; no te quedes en 1 frase genérica. "
    "NO invoques generate_image. NO preguntes datos del producto que ya están arriba."
)


def wants_fitline_knowledge(text: str) -> bool:
    """True si el mensaje habla de PM/FitLine o productos curados del catálogo."""
    t = (text or "").strip()
    if not t:
        return False
    if _BRAND.search(t):
        return True
    if _DISTINCT_PRODUCTS.search(t):
        return True
    if _BASICS.search(t) and (_BRAND.search(t) or _DISTINCT_PRODUCTS.search(t)):
        return True
    if _BASICS.search(t) and re.search(
        r"\b(?:fitline|fit\s*line|suplemento|nutrici[oó]n|franquicia)\b",
        t,
        re.I,
    ):
        return True
    return False


def _section_title(key: str) -> str:
    for section_key, title in SECTION_ORDER:
        if section_key == key:
            return title
    return key.replace("_", " ").title()


@lru_cache(maxsize=1)
def format_fitline_knowledge_for_prompt(*, max_chars: int = 14_000) -> str:
    """Aplana secciones curadas del plugin FitLine para el system prompt."""
    plugin = get_plugin(OPPORTUNITY_ID)
    if not plugin:
        return ""
    curated = plugin.get("curated") or {}
    sections = curated.get("sections") or {}
    if not isinstance(sections, dict) or not sections:
        return ""

    as_of = str(curated.get("as_of") or "").strip() or "curado"
    title = str(plugin.get("title") or "PM International / FitLine")
    parts: list[str] = [
        f"CONOCIMIENTO CURADO — {title} (módulo Oportunidades, as_of={as_of}).",
        _PROMPT_RULES,
    ]

    for key, section_title in SECTION_ORDER:
        row = sections.get(key)
        if not isinstance(row, dict):
            continue
        body = str(row.get("body") or "").strip()
        if not body:
            continue
        parts.append(f"### {section_title}\n{body}")

    # Cualquier sección curada no listada en SECTION_ORDER
    known = {k for k, _ in SECTION_ORDER}
    for key, row in sections.items():
        if key in known or not isinstance(row, dict):
            continue
        body = str(row.get("body") or "").strip()
        if body:
            parts.append(f"### {_section_title(str(key))}\n{body}")

    text = "\n\n".join(parts).strip()
    if len(text) > max_chars:
        text = text[: max_chars - 40].rstrip() + "\n\n…[contexto FitLine truncado]"
    return text


def append_fitline_knowledge_if_needed(system: str, user_text: str) -> str:
    """Añade el bloque FitLine al system prompt cuando el turno lo requiere."""
    if not wants_fitline_knowledge(user_text):
        return system
    block = format_fitline_knowledge_for_prompt()
    if not block:
        return system
    from app.services.chat_intents import is_text_ideation_request

    base = (system or "").rstrip()
    out = f"{base}\n\n{block}" if base else block
    if is_text_ideation_request(user_text):
        out = f"{out.rstrip()}\n\n{_FITLINE_CONTENT_DELIVERY_RULES}"
    return out


def fitline_plugin_snapshot() -> dict[str, Any] | None:
    """Utilidad de tests / diagnóstico — plugin crudo o None."""
    return get_plugin(OPPORTUNITY_ID)
