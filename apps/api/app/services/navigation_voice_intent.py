"""Intenciones de navegación por voz — corrige STT y evita que el LLM bloquee búsquedas."""

from __future__ import annotations

import re
from typing import Any

from app.services.cognitive_intents import is_navigation_confirm
from app.services.navigation_session import (
    get_navigation_pending,
    get_place_options,
    get_route,
    is_navigating,
)
from app.services.retell_llm_types import Utterance

# Retell/STT confunde "Walmart" con "arma(s)" con frecuencia en español.
_ARMA_WALMART = re.compile(r"\barmas?\b", re.I)
_WALMART_HINT = re.compile(r"\bwalmarts?\b", re.I)
_NAV_CONTEXT = re.compile(
    r"\b(cercan[oa]s?|cerca|ir\s+a|ll[eé]vame|busca(?:r)?|mapa|naveg|viaje|"
    r"gasolinera|supermercado|tienda|destino|modo\s+conducir)\b",
    re.I,
)

_OPEN_MAP = re.compile(
    r"\b(?:activar|abre|abrir|muestra|mostrar|pon(?:er)?)\s+(?:el\s+)?mapa\b|"
    r"\bmodo\s+conducir\b|"
    r"\bnavegaci[oó]n\s+(?:gps|mapa)\b",
    re.I,
)

_SHOW_ROUTE = re.compile(
    r"\b(?:mu[eé]stra(?:me)?|mostrar|ense[nñ]a(?:me)?|traza(?:me)?|calcula(?:me)?)\s+"
    r"(?:la\s+)?ruta\b|"
    r"\bruta\s+por\s+favor\b",
    re.I,
)

_START_ROUTE = re.compile(
    r"\b(?:inicia|iniciar|arranca|arrancar|empieza|empezar)\s+"
    r"(?:(?:la|el)\s+)?(?:ruta|navegaci[oó]n|viaje|gps)\b|"
    r"\bcomienza(?:\s+la)?\s+navegaci[oó]n\b",
    re.I,
)

_AGENT_ASK_START = re.compile(
    r"\b(iniciamos|inicio el viaje|iniciar(?:\s+(?:el\s+)?viaje|ruta)?|"
    r"m[aá]s cercano|cu[aá]l prefiere|toque iniciar)\b",
    re.I,
)

_EXTRACT_PLACE = re.compile(
    r"(?:"
    r"(?:busca(?:r)?|busque)\s+(?:alg[uú]n|alguna|un|una|el|la|me)?\s*"
    r"|(?:quiero|necesito|deseo)\s+(?:ir|irme)\s+(?:a\s+)?(?:alg[uú]n|alguna|un|una|el|la)?\s*"
    r"|(?:ir|vamos|ll[eé]vame)\s+(?:a\s+)?(?:alg[uú]n|alguna|un|una|el|la)?\s*"
    r")"
    r"(?P<place>.+?)"
    r"(?:\s+(?:m[aá]s\s+)?cercan[oa]s?|\s+cerca|\s+por\s+favor)?"
    r"\s*$",
    re.I,
)

_ABSTRACT_PLACE_WORDS = frozenset(
    {
        "inmenso",
        "potencial",
        "historia",
        "resumen",
        "explicación",
        "explicacion",
        "conversación",
        "conversacion",
        "charla",
        "idea",
        "ideas",
        "proyecto",
        "plan",
        "estrategia",
        "contenido",
        "mensaje",
        "correo",
        "email",
    }
)

_STRIP_FILLERS = re.compile(
    r"^(?:por\s+favor|señor|senor|ced|a|al|el|la|un|una|alg[uú]n|alguna)\s+",
    re.I,
)

# Frases conversacionales tras "ir a / quiero …" — no son destinos GPS.
_NON_PLACE_HEAD = re.compile(
    r"^(?:"
    r"dormir|contar(?:te|le)?|decir(?:te|le)?|hablar|explicar(?:te|le)?|"
    r"preguntar(?:te|le)?|saber|comentar(?:te|le)?|mostrar(?:te|le)?|"
    r"revisar|ver(?:te|le)?|escuchar|ayudar(?:te|le)?|contarte|"
    r"mis\s+correos|mis\s+emails|el\s+correo"
    r")\b",
    re.I,
)

_QUESTION_ONLY = re.compile(r"^\s*¿.+?\?\s*$")


def _has_navigation_context(*, text: str, ctx: str = "", agent_last: str = "") -> bool:
    blob = f"{text} {ctx} {agent_last}"
    if _NAV_CONTEXT.search(blob):
        return True
    if _OPEN_MAP.search(blob):
        return True
    if _AGENT_ASK_START.search(agent_last):
        return True
    if _WALMART_HINT.search(text):
        return True
    return False


def _is_valid_place_candidate(place: str, *, text: str, ctx: str = "") -> bool:
    if not place or len(place) < 2:
        return False
    if _NON_PLACE_HEAD.match(place.strip()):
        return False
    tokens = {w.lower() for w in re.findall(r"[a-záéíóúñ]+", place, flags=re.I)}
    if tokens and tokens.issubset(_ABSTRACT_PLACE_WORDS):
        return False
    if any(tok in _ABSTRACT_PLACE_WORDS for tok in tokens) and not _NAV_CONTEXT.search(
        f"{text} {ctx}"
    ):
        return False
    blob = f"{text} {ctx}"
    if re.search(r"\b(?:alg[uú]n|alguna|un|una)\s+", text, re.I):
        if not re.search(r"\bcercan[oa]s?\b", blob, re.I) and not _WALMART_HINT.search(text):
            if not _should_correct_arma_to_walmart(text, context=ctx):
                return False
    return True


def is_plausible_place_query(query: str, *, user_text: str = "") -> bool:
    """Evita que Gemini envíe búsquedas de mapa con frases conversacionales."""
    q = normalize_navigation_query((query or "").strip(), context=user_text)
    if not q or len(q) < 2:
        return False
    return _is_valid_place_candidate(q, text=user_text or q, ctx=user_text)


def _normalize(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def _transcript_blob(transcript: list[Utterance]) -> str:
    return " ".join((u.content or "").strip() for u in transcript[-12:] if (u.content or "").strip())


def _last_agent_line(transcript: list[Utterance]) -> str:
    for u in reversed(transcript[-12:]):
        if (u.role or "").lower() == "agent" and (u.content or "").strip():
            return str(u.content).strip()
    return ""


def _should_correct_arma_to_walmart(text: str, *, context: str = "") -> bool:
    if not _ARMA_WALMART.search(text):
        return False
    blob = f"{text} {context}"
    if _WALMART_HINT.search(blob):
        return True
    if _NAV_CONTEXT.search(blob):
        return True
    if re.search(r"\b(?:supermercado|tienda|comprar|compras)\b", blob, re.I):
        return True
    return False


def normalize_navigation_query(query: str, *, context: str = "") -> str:
    """Corrige errores STT comunes antes de buscar lugares."""
    q = (query or "").strip()
    if not q:
        return q

    if _should_correct_arma_to_walmart(q, context=context):
        q = _ARMA_WALMART.sub("Walmart", q, count=1)
        q = re.sub(r"\b(?:alg[uú]n|alguna|un|una)\s+", "", q, flags=re.I).strip()
        if re.fullmatch(r"(?i)walmart", q) or q.lower().startswith("walmart"):
            return "Walmart"

    q = re.sub(r"\bguarmar\b", "Walmart", q, flags=re.I)
    q = re.sub(r"\bwallmart\b", "Walmart", q, flags=re.I)
    q = re.sub(r"\bwal\s*mart\b", "Walmart", q, flags=re.I)

    while True:
        cleaned = _STRIP_FILLERS.sub("", q).strip()
        if cleaned == q:
            break
        q = cleaned
    return q.strip() or query.strip()


def extract_place_query(user_text: str) -> str | None:
    text = (user_text or "").strip()
    if not text:
        return None

    m = _EXTRACT_PLACE.search(text)
    if m:
        place = normalize_navigation_query(m.group("place").strip(), context=text)
        if _is_valid_place_candidate(place, text=text):
            return place

    if _ARMA_WALMART.search(text) and _NAV_CONTEXT.search(text):
        return "Walmart"

    if _WALMART_HINT.search(text) and _NAV_CONTEXT.search(text):
        return "Walmart"

    # "Walmart más cercano" sin verbo
    m2 = re.search(
        r"(?P<place>[A-Za-zÁÉÍÓÚáéíóúñÑ\s]{2,40}?)\s+(?:m[aá]s\s+)?cercan[oa]s?\s*$",
        text,
        re.I,
    )
    if m2:
        place = normalize_navigation_query(m2.group("place").strip(), context=text)
        if place and place.lower() not in {"algún", "alguna", "un", "una", "el", "la"}:
            return place

    return None


def resolve_open_map_request(user_text: str) -> bool:
    text = (user_text or "").strip()
    if not text:
        return False
    if _QUESTION_ONLY.match(text) and not _OPEN_MAP.search(text):
        return False
    norm = _normalize(text)
    if norm in {"mapa", "activar mapa", "abre mapa", "abrir mapa", "modo conducir"}:
        return True
    return bool(_OPEN_MAP.search(text))


def resolve_show_route_request(user_text: str) -> bool:
    """True cuando pide ver/trazar la ruta sin arrancar la guía aún."""
    text = (user_text or "").strip()
    if not text:
        return False
    return bool(_SHOW_ROUTE.search(text))


def resolve_start_route_request(user_text: str) -> bool:
    """True cuando pide iniciar navegación en vivo."""
    text = (user_text or "").strip()
    if not text:
        return False
    if resolve_show_route_request(text) and not _START_ROUTE.search(text):
        return False
    return bool(_START_ROUTE.search(text)) or is_navigation_confirm(text)


_GENERIC_PLACE_QUERY = re.compile(
    r"\b("
    r"walmart|target|costco|sam'?s|lidl|aldi|"
    r"mcdonalds?|starbucks|burger\s*king|wendy|"
    r"farmacia|gasolinera|hospital|urgencias|"
    r"mercado|supermercado|tienda|banco|cajero|atm|"
    r"restaurante|cafeter[ií]a|comida|"
    r"m[aá]s\s+cercan[oa]s?|cercanos?|nearby|cerca(?:\s+de\s+m[ií])?|"
    r"alg[uú]n|cualquier"
    r")\b",
    re.I,
)


def is_generic_place_query(query: str) -> bool:
    """Categoría (varios resultados) vs nombre propio específico (un POI)."""
    q = (query or "").strip()
    if not q:
        return False
    return bool(_GENERIC_PLACE_QUERY.search(q))


def resolve_navigation_place_search(
    user_text: str,
    transcript: list[Utterance],
) -> dict[str, str] | None:
    """
    Detecta búsqueda de lugar cercano (Walmart, gasolinera, etc.)
    y corrige STT antes de que Gemini interprete "arma" como armas.
    """
    last = (user_text or "").strip()
    if not last:
        return None

    ctx = _transcript_blob(transcript)
    agent_last = _last_agent_line(transcript)
    norm = _normalize(last)

    # Confirmación tras "¿se refiere a Walmart?"
    if norm in {"si", "sí", "exacto", "correcto", "así es", "ese", "ese mismo"}:
        if _WALMART_HINT.search(agent_last) or _ARMA_WALMART.search(agent_last):
            return {"query": "Walmart", "open_map": "true"}

    if resolve_open_map_request(last) and not extract_place_query(last):
        return None

    place = extract_place_query(last)
    if not place:
        # "algún arma más cercano" suelto
        if _should_correct_arma_to_walmart(last, context=ctx):
            return {"query": "Walmart", "open_map": "true"}
        return None

    if not _has_navigation_context(text=last, ctx=ctx, agent_last=agent_last):
        return None

    place = normalize_navigation_query(place, context=f"{last} {ctx}")
    if not place:
        return None

    return {"query": place, "open_map": "true"}


def resolve_navigation_confirm(
    user_text: str,
    transcript: list[Utterance],
    *,
    user_id: str | None = None,
) -> dict[str, Any] | None:
    """
    Detecta confirmación para iniciar ruta tras búsqueda de lugares
    o para arrancar guía cuando la ruta ya está calculada.
    """
    last = (user_text or "").strip()
    if not last or not is_navigation_confirm(last):
        return None

    agent_last = _last_agent_line(transcript)
    pending = get_navigation_pending(user_id) if user_id else {"pending": False, "index": 0}
    agent_asked = bool(_AGENT_ASK_START.search(agent_last))
    if not pending.get("pending") and not agent_asked:
        return None

    if user_id and is_navigating(user_id):
        return None

    route = get_route(user_id) if user_id else None
    if route:
        return {"action": "begin_navigation"}

    options = get_place_options(user_id) if user_id else []
    if not options and not pending.get("pending"):
        return None

    idx = int(pending.get("index") or 0)
    if options and idx >= len(options):
        idx = 0
    destination = pending.get("destination")
    if not destination and options:
        destination = options[idx] if idx < len(options) else options[0]

    return {
        "action": "start_navigation",
        "index": idx,
        "destination": destination,
    }
