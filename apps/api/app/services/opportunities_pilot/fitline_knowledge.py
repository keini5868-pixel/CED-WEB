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

# Marcas / empresa / fundadores / sede / credenciales distintivas
_BRAND = re.compile(
    r"\b(?:"
    r"fit\s*-?\s*line|fitline|"
    r"pm[\s\-]?international|pm\s*international|"
    r"pme\s*business|pmebusiness|"
    r"pm[\s\-]?income\s*plan|"
    r"rolf\s+sorg|vicki\s+sorg|"
    r"pm\s*we\s*care|cologne\s*list|lista\s*(?:de\s*)?colonia|"
    r"nutrient\s+transport\s+concept"
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
    "NO inventes productos, precios de entrada, comisiones, % del Income Plan 2026, "
    "claims de salud ni cifras. "
    "DETECCIÓN RÁPIDA — PRIORIDAD ABSOLUTA: responde YA con este bloque. "
    "PROHIBIDO invocar search_web / Tavily. "
    "PROHIBIDO decir «Investigando, señor», «investigando», «déjeme consultar», "
    "«consultando», «voy a buscar», «busco en internet» o cualquier filler de "
    "búsqueda si el pedido se cubre aquí (historia, NTC, productos, credenciales, "
    "deporte, prospección, precios de lista de producto de referencia). "
    "Si falta precio de entrada al negocio o % del Income Plan: dilo y remite a "
    "Partner Area / enlace de patrocinio — NO busques en la web para inventar cifras. "
    "Solo use búsqueda web si el usuario pide EXPLÍCITAMENTE internet/noticias/"
    "datos de hoy Y el hecho concreto no está en este bloque. "
    "NO preguntes qué es un producto o marca que ya aparece aquí: aplícalo YA "
    "(ideas de venta, copy, prompts, prospección, estrategia). "
    "Si pide CONTENIDO / IDEA / COPY / PROMPT / GUION / PROSPECCIÓN de texto sobre "
    "FitLine o un producto de este catálogo: ENTREGA el texto completo YA, usando "
    "hechos de este bloque + playbook de marketing CED "
    "(hooks específicos, PAS/AIDA/BAB internamente, terminología correcta). "
    "NO generes imagen. NO digas «no tengo info» si el hecho está aquí. "
    "NO abras con preguntas básicas (qué es, para qué sirve) — ya lo sabes."
)

_FITLINE_CONTENT_DELIVERY_RULES = (
    "ENTREGA FITLINE/PM (texto): responde con contenido útil y listo para usar "
    "(idea, copy, prompt delimitado con ---, guion, caption o secuencia de "
    "prospección). Combina hechos verificables de esta ficha (NTC, productos, "
    "credenciales, escala) con criterio de marketing CED. "
    "Sé concreto y accionable; no te quedes en 1 frase genérica. "
    "NO invoques generate_image. NO preguntes datos del producto que ya están arriba. "
    "NO inventes comisiones ni precios de entrada."
)

# Tarjeta corta al inicio del bloque — los LLM suelen ignorar el final del system.
_FACT_CARD = (
    "HECHOS OBLIGATORIOS FITLINE/PM (NO contradiga ni «corrija» estos datos):\n"
    "• Fundación: 1993 en Speyer, Alemania, por Rolf Sorg (junto a Vicki Sorg).\n"
    "• Sede actual: Schengen, Luxemburgo (desde 2015).\n"
    "• Escala: 40–45+ países; 1.000+ empleados; $3.22 mil millones (2025); "
    "#6 venta directa (DSN Top 100); 1.000+ millones de productos FitLine vendidos.\n"
    "• NTC = Nutrient Transport Concept (NO «Nutrient Timing»). "
    "Nutrientes cuándo y dónde el cuerpo los necesita, a nivel celular.\n"
    "• Calidad: 70+ patentes; Univ. Trier + ELAB; QR de análisis independientes; "
    "manufactura en Alemania bajo GMP.\n"
    "• Anti-dopaje: Cologne List® (~20 años; PM socio fundador); 0 casos positivos "
    "en historial de análisis.\n"
    "• Legalidad: Frankfurt 2011; TÜV Hessen desde 2013 (anual).\n"
    "• Deporte: ATP Tour, Swiss Sports Aid, Comité Paralímpico Corea; federaciones "
    "esquí DE/AT/PL, hockey/ciclismo/atletismo DE; 1.000+ atletas / 85+ disciplinas.\n"
    "• Social: Fundación PM We Care — $3M+ donados; 800+ apadrinamientos de niños.\n"
    "• Productos clave: Optimal Set (insignia), PowerCocktail, Activize (energía), "
    "Restorate (minerales/recuperación), Basics (fibra/probióticos).\n"
    "• NO invente años de fundación, expansión de NTC, ni productos estrella "
    "fuera de esta lista. Precios de entrada / Income Plan actualizado → Partner Area "
    "/ material del patrocinador (NO inventar ni buscar en web para completar)."
)

_USER_TURN_PREFIX = (
    "[CED-OPORTUNIDADES FitLine/PM] Use SOLO el conocimiento Oportunidades del "
    "system (tarjeta de hechos + secciones). "
    "NTC = Nutrient Transport Concept. Fundación 1993 Speyer / Rolf Sorg. "
    "Sede Schengen desde 2015. PROHIBIDO decir investigando o buscar en internet. "
    "NO invente productos ni fechas.\n\n"
)


def fitline_user_turn_prefix(user_text: str) -> str:
    """Prefijo duro en el mensaje del usuario para anclar hechos en chat/voz."""
    if not prefers_fitline_over_web(user_text):
        return ""
    return _USER_TURN_PREFIX


def with_fitline_user_prefix(user_text: str) -> str:
    prefix = fitline_user_turn_prefix(user_text)
    if not prefix:
        return user_text
    return f"{prefix}{user_text}"


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
    # NTC / Schengen / Speyer / Cologne / dopaje / GMP / We Care con contexto.
    if re.search(
        r"\b(?:ntc|schengen|speyer|cologne|dopaje|anti[\s\-]?dopaje|gmp|"
        r"we\s*care|atp\s*tour)\b",
        t,
        re.I,
    ) and re.search(
        r"\b(?:fitline|fit\s*line|pm|nutri|suplement|franquicia|sorg|"
        r"cologne|dopaje|atleta|paral[ií]mpic)\b",
        t,
        re.I,
    ):
        return True
    return False


# Solo override explícito: internet/noticias/datos de hoy — no «precio de Restorate».
_EXPLICIT_LIVE_WEB = re.compile(
    r"(?is)\b(?:"
    r"busca(?:r|me)?\s+(?:en\s+)?(?:internet|la\s+web|google)|"
    r"investiga(?:r|me)?\s+(?:en\s+)?(?:internet|la\s+web)|"
    r"en\s+(?:internet|google|la\s+web)\b|"
    r"noticias?\b|"
    r"(?:precio|cuesta|cotiza|vale).{0,48}\b(?:hoy|actual|ahora)\b|"
    r"\b(?:hoy|ahora|actual)\b.{0,48}\b(?:precio|cuesta|cotiza)\b|"
    r"informaci[oó]n\s+actualizada|datos\s+actuales|titulares|última\s+hora"
    r")"
)


def fitline_explicit_live_web_override(text: str) -> bool:
    """True solo si el usuario pide web/noticias/datos de hoy de forma explícita."""
    t = (text or "").strip()
    if not t:
        return False
    try:
        from app.services.cognitive_intents import is_news_intent, is_weather_intent

        if is_news_intent(t) or is_weather_intent(t):
            return True
    except Exception:  # noqa: BLE001
        pass
    return bool(_EXPLICIT_LIVE_WEB.search(t))


def prefers_fitline_over_web(text: str) -> bool:
    """FitLine/PM: usar Oportunidades primero; web solo con override explícito."""
    if not wants_fitline_knowledge(text):
        return False
    return not fitline_explicit_live_web_override(text)


def _section_title(key: str) -> str:
    for section_key, title in SECTION_ORDER:
        if section_key == key:
            return title
    return key.replace("_", " ").title()


@lru_cache(maxsize=4)
def format_fitline_knowledge_for_prompt(*, max_chars: int = 16_000) -> str:
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
        _FACT_CARD,
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
    from app.domain.ced_sales_marketing_playbook import (
        append_sales_marketing_playbook_if_needed,
    )
    from app.services.chat_intents import is_text_ideation_request

    base = (system or "").rstrip()
    out = f"{base}\n\n{block}" if base else block
    # Prospección / copy FitLine también lleva el playbook de marketing.
    out = append_sales_marketing_playbook_if_needed(out, user_text)
    if is_text_ideation_request(user_text) or re.search(
        r"\bprospecci[oó]n|prospectar|contenido|campa[nñ]a\b",
        user_text or "",
        re.I,
    ):
        out = f"{out.rstrip()}\n\n{_FITLINE_CONTENT_DELIVERY_RULES}"
    return out


def fitline_plugin_snapshot() -> dict[str, Any] | None:
    """Utilidad de tests / diagnóstico — plugin crudo o None."""
    return get_plugin(OPPORTUNITY_ID)
