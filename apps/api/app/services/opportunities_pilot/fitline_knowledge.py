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
# Evitar nombres genéricos solos (endurance, whey, protein, omega 3, lutein).
# Nota: SKUs con «+» (Generation 50+, Women+) no usan \\b final — falla tras «+».
_DISTINCT_PRODUCTS = re.compile(
    r"(?:"
    r"\b(?:"
    # Nutrición base
    r"activize|activise|oxyplus|"
    r"restorate|"
    r"power\s*-?\s*cocktail|powercocktail|"
    r"optimal[\s\-]?set|"
    # Deporte / fitness (nombres compuestos)
    r"protein\s*max|"
    r"proshape|"
    r"fitness[\s\-]?drink|"
    r"powermeal(?:\s*bar)?|"
    r"joint[\s\-]?health|"
    # Control de peso
    r"get\s*in\s*shape|"
    r"proshape\s*all[\s\-]?in[\s\-]?1|"
    r"proshape\s*2[\s\-]?go|"
    # Especiales
    r"zellschutz|antioxy|"
    r"munogen|"
    r"basen\s*plus|"
    r"d[\s\-]?drink|"
    r"herbaslim|"
    r"activize\s*power\s*drink|"
    r"feel\s*good\s*yoghurt|feel\s*good\s*yogurt|"
    r"microsolve|heart\s*duo|heartduo|"
    r"q10\s*plus|"
    r"isoflavona|isoflavone|"
    # Otras líneas frecuentes
    r"topshape|"
    r"ultimate\s+young|hydrating[\s\-]?shot"
    r")\b|"
    r"generation\s*50\+|"
    r"women\+|men\+|"
    r"\bib\s*5\b|ib⁵"
    r")",
    re.I,
)

# Genéricos: solo con marca FitLine/PM cerca
_AMBIGUOUS_SKUS = re.compile(
    r"\b(?:endurance|whey|fruit\s*bar|protein(?!\s*max)|lutein|omega\s*3)\b",
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

# Capa persuasiva fija (system prompt) — CERO tools / Tavily / modelos extra.
_FITLINE_SALES_CLOSER = """
# PM/FITLINE — ASESOR COMERCIAL (SOLO ESTE TEMA)
Aplica ÚNICAMENTE mientras la conversación sea sobre PM International / FitLine /
productos / negocio de red de franquicias. En CUALQUIER otro tema: personalidad CED normal
(sin presión de venta).

ROL: mentor comercial experimentado. Informas con hechos reales de la ficha Oportunidades
y ayudas a decidir con claridad — no eres enciclopedia neutra ni telemarketer.
Usa hechos SOLO de la ficha. PROHIBIDO search_web / Tavily / «investigando» /
modelos extra para inventar persuasión o precios.

ESTILO «VENDER SIN PARECER QUE VENDE»:
1) Primero responde completo y natural a lo que pidió (producto, NTC, negocio, objeción).
2) Brinda toda la información real disponible en la ficha — sin retener datos para «cerrar».
3) Solo en puntos clave (interés claro, objeción, «¿cómo empiezo?», comparación,
   duda de precio/tiempo, o pedido explícito de cierre) añade UNA inclinación sutil:
   una pregunta estratégica de avance. El resto del tiempo: valor + claridad, sin pitch.
4) Voz — profundidad tipo Jarvis Retell:
   - Producto o negocio (p. ej. Restorate, NTC, franquicia): responde COMPLETO en el turno
     (unas 5–10 oraciones o un párrafo denso). Incluye para qué sirve, minerales/beneficios
     relevantes, NTC y cuándo tomarlo si está en la ficha.
   - PROHIBIDO acortar con «¿quieres más información?», «¿te doy más detalle?»,
     «¿quieres que profundice?» u ofertas vacías de seguir. Entrega el valor YA.
   - Máximo UNA pregunta de avance solo si hay interés claro de compra/inscripción
     (objeción, «cómo empiezo»). Nunca cuestionario ni muletilla de «más info».

PALABRAS CLAVE (úsalas con naturalidad cuando encaje, no las listes):
oportunidad, transformación, pertenecer / equipo, dar el paso, resultado,
credibilidad (NTC, Cologne List, atletas, escala), libertad de tiempo/negocio —
sin promesas de ingreso inventadas ni % del Income Plan.

CIERRE ESTRATÉGICO (solo momento oportuno — no en cada frase):
1) Detecta la objeción real (tiempo, dinero, miedo a vender, «no sé si es para mí»).
2) Resuelve con un hecho verificable de la ficha + ejemplo cotidiano.
3) UNA pregunta de avance, p. ej.:
   - «¿Qué le frena más hoy: el tiempo, la inversión inicial, o no saber cómo hablarle a la gente?»
   - «Si probara solo el Optimal-Set / Activize esta semana, ¿qué resultado querría notar primero?»
   - «¿Quiere que le arme el siguiente paso con su patrocinador, o prefiere primero un pitch de 30 segundos?»

PUENTE PLAN DE FRANQUICIA (después de explicar negocio/productos + interés real):
- Ofrece UNA vez, con naturalidad: «Tengo un módulo donde podemos organizar un plan
  de acción de crecimiento para tu nueva franquicia — ¿quieres que lo armemos juntos?»
- Usa siempre la palabra «franquicia» (no «socio» para nombrar el plan).
- Si acepta: arma metas/pasos concretos con hechos FitLine y llama
  guardar_plan_crecimiento_franquicia. Luego guía a OPPS con abrir_oportunidades_fitline
  (enlace de inscripción/patrocinio al final de Oportunidades).
- Si ya se inscribió y quiere su propio enlace: actualizar_enlace_patrocinio_fitline.

PROHIBIDO: inventar precios de entrada, comisiones o Income Plan; forzar venta en cada turno;
sonar a telemarketing; leer instrucciones internas en voz alta; cambiar la personalidad CED
fuera de FitLine/PM.
""".strip()


def fitline_sales_closer_overlay() -> str:
    """Overlay persuasivo fijo (interno). Sin costo de tools."""
    return _FITLINE_SALES_CLOSER

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
    "• Catálogo (ampliado): Nutrición base — Optimal-Set, PowerCocktail "
    "(+ Junior), Restorate, Generation 50+, Activize Oxyplus, Basics; "
    "Deporte — Endurance, Protein/Protein Max, ProShape Amino, Whey, "
    "Fitness-Drink, PowerMeal Bar, Joint-Health Set; "
    "Peso — Get in Shape, ProShape All-in-1 / 2 Go; "
    "Especiales — Zellschutz/Antioxy, IB5, Munogen, Basen Plus, D-Drink, "
    "Herbaslim Tea, Fruit Bar, Activize Power Drink, Feel Good Yoghurt, "
    "microSolve (HeartDuo, Omega 3, Q10 Plus, Lutein, Isoflavona). "
    "Belleza y más peso: confirmar en Partner Area / tienda local.\n"
    "• NO invente SKUs ni claims fuera de esta lista. Precios de entrada / "
    "Income Plan actualizado → Partner Area / material del patrocinador "
    "(NO inventar ni buscar en web para completar)."
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
    if _AMBIGUOUS_SKUS.search(t) and (
        _BRAND.search(t)
        or re.search(r"\b(?:fitline|fit\s*line|pm\s*international|suplemento)\b", t, re.I)
    ):
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
        _FITLINE_SALES_CLOSER,
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


@lru_cache(maxsize=2)
def format_fitline_knowledge_lean_for_voice(*, max_chars: int = 7_500) -> str:
    """Versión compacta para CED Cierre Realtime — hechos + closer, menos tokens."""
    plugin = get_plugin(OPPORTUNITY_ID)
    if not plugin:
        return format_fitline_knowledge_for_prompt(max_chars=max_chars)
    curated = plugin.get("curated") or {}
    sections = curated.get("sections") or {}
    as_of = str(curated.get("as_of") or "").strip() or "curado"
    title = str(plugin.get("title") or "PM International / FitLine")
    lean_keys = (
        "what_is",
        "products",
        "business_model",
        "how_to_start",
        "objections",
        "credentials",
    )
    parts: list[str] = [
        f"CONOCIMIENTO INTERNO CED — {title} (Oportunidades, as_of={as_of}).",
        "COSTO CERO DE HERRAMIENTAS EXTERNAS: responde SOLO con este bloque. "
        "PROHIBIDO search_web, Tavily, imágenes, YouTube, mapas o «investigando».",
        _FACT_CARD,
        _FITLINE_SALES_CLOSER,
    ]
    if isinstance(sections, dict):
        for key in lean_keys:
            row = sections.get(key)
            if not isinstance(row, dict):
                continue
            body = str(row.get("body") or "").strip()
            if not body:
                continue
            if len(body) > 900:
                body = body[:880].rstrip() + "…"
            parts.append(f"### {_section_title(key)}\n{body}")
    text = "\n\n".join(parts).strip()
    if len(text) > max_chars:
        text = text[: max_chars - 40].rstrip() + "\n\n…[contexto FitLine lean]"
    return text


def append_fitline_knowledge_if_needed(
    system: str,
    user_text: str,
    *,
    force: bool = False,
) -> str:
    """Añade el bloque FitLine al system prompt cuando el turno lo requiere."""
    if not force and not wants_fitline_knowledge(user_text):
        return system
    block = format_fitline_knowledge_for_prompt()
    if not block:
        return system
    from app.domain.ced_sales_marketing_playbook import (
        append_sales_marketing_playbook_if_needed,
    )
    from app.services.chat_intents import is_text_ideation_request

    base = (system or "").rstrip()
    if "HECHOS OBLIGATORIOS FITLINE" in base or "CONOCIMIENTO CURADO — PM International" in base:
        out = base
    else:
        out = f"{base}\n\n{block}" if base else block
    # Prospección / copy FitLine también lleva el playbook de marketing.
    out = append_sales_marketing_playbook_if_needed(out, user_text or "fitline")
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
