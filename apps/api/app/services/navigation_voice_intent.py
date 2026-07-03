"""Intenciones de navegación por voz — corrige STT y evita que el LLM bloquee búsquedas."""

from __future__ import annotations

import re

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

_EXTRACT_PLACE = re.compile(
    r"(?:"
    r"(?:busca(?:r)?|busque)\s+(?:alg[uú]n|alguna|un|una|el|la|me)?\s*"
    r"|(?:quiero|necesito|deseo)\s+(?:ir|irme)\s+(?:a\s+)?(?:alg[uú]n|alguna|un|una|el|la)?\s*"
    r"|(?:ir|vamos|ll[eé]vame)\s+(?:a\s+)?(?:alg[uú]n|alguna|un|una|el|la)?\s*"
    r"|(?:alg[uú]n|alguna|un|una)\s+"
    r")"
    r"(?P<place>.+?)"
    r"(?:\s+(?:m[aá]s\s+)?cercan[oa]s?|\s+cerca|\s+por\s+favor)?"
    r"\s*$",
    re.I,
)

_STRIP_FILLERS = re.compile(
    r"^(?:por\s+favor|señor|senor|ced|a|al|el|la|un|una|alg[uú]n|alguna)\s+",
    re.I,
)


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
        if len(place) >= 2:
            return place

    if _ARMA_WALMART.search(text) and _NAV_CONTEXT.search(text):
        return "Walmart"

    if _WALMART_HINT.search(text):
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
    norm = _normalize(text)
    if norm in {"mapa", "activar mapa", "abre mapa", "abrir mapa", "modo conducir"}:
        return True
    return bool(_OPEN_MAP.search(text))


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

    place = normalize_navigation_query(place, context=f"{last} {ctx}")
    if not place:
        return None

    return {"query": place, "open_map": "true"}
