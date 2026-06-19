"""Utilidades del protocolo Retell Custom LLM."""

from __future__ import annotations

import re

from app.services.cognitive_intents import (
    is_news_intent,
    is_volatile_query,
    is_weather_intent,
    is_web_research_intent,
    normalize_text,
)
from app.services.retell_llm_types import Utterance

_ECHO_USER_LINES = frozenset(
    {
        "a su servicio, señor",
        "a su servicio señor",
        "a su servicio, señor.",
        "a su servicio señor.",
    }
)

_SMALL_TALK = frozenset(
    {
        "hola",
        "hola cómo estás",
        "hola como estas",
        "hola, ¿cómo estás?",
        "hola, como estas?",
        "buenos días",
        "buenas tardes",
        "buenas noches",
        "cómo estás",
        "como estas",
        "qué tal",
        "que tal",
        "okay",
        "ok",
        "sí",
        "si",
    }
)

_GENERIC_AGENT_LINES = frozenset(
    {
        "operativo y a su servicio, señor.",
        "operativo y a su servicio señor.",
        "a su servicio, señor.",
    }
)

_ACK_ONLY = frozenset({"ok", "okay", "sí", "si", "vale", "bien", "yes", "news", "noticias"})

_WEB_FRAGMENT_HINTS = re.compile(
    r"\b(busca|buscar|buscame|investiga|precio|cotiza|clima|tiempo|temperatura|"
    r"noticia|ultim|dime|dame|cuanto|cuesta|hoy|internet|google|web|mercado|"
    r"tendencia|actualidad|significa|vale|creatina|suplemento)\b",
    re.I,
)

_FRAGMENT_PREFIX = re.compile(
    r"^(de|del|la|el|los|las|en|con|para|y|que|qué|en\s+estados)\b",
    re.I,
)


def _normalize(text: str) -> str:
    cleaned = (text or "").strip().lower()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.rstrip(".,!?¿¡")


def _user_lines(transcript: list[Utterance]) -> list[str]:
    return [
        (u.content or "").strip()
        for u in transcript
        if u.role == "user" and (u.content or "").strip()
    ]


def last_user_text(transcript: list[Utterance]) -> str:
    lines = _user_lines(transcript)
    return lines[-1] if lines else ""


def merged_user_query(transcript: list[Utterance], *, max_lines: int = 2) -> str:
    """Une solo fragmentos cortos del mismo turno — no arrastra temas viejos."""
    lines = _user_lines(transcript)
    if not lines:
        return ""
    if len(lines) == 1:
        return lines[0]
    last = lines[-1]
    prev = lines[-2]
    if _is_fragment_continuation(last, prev):
        return f"{prev} {last}".strip()
    return last


def _is_fragment_continuation(last: str, prev: str) -> bool:
    """True solo si `last` completa la frase anterior (ej. 'de Estados Unidos')."""
    ln = _normalize(last)
    pn = _normalize(prev)
    if not ln or not pn:
        return False
    if ln in _ACK_ONLY or pn in _ACK_ONLY:
        return False
    if _needs_internet_lookup(last) and not _FRAGMENT_PREFIX.search(ln):
        if is_news_intent(last) or is_weather_intent(last) or is_web_research_intent(last):
            return False
    if len(ln.split()) <= 4 and _FRAGMENT_PREFIX.search(ln):
        return True
    if len(ln.split()) <= 2 and _needs_internet_lookup(pn):
        return True
    return False


def _needs_internet_lookup(text: str) -> bool:
    if is_weather_intent(text) or is_news_intent(text) or is_web_research_intent(text):
        return True
    norm = normalize_text(text)
    if len(norm) < 4 or norm in _ACK_ONLY:
        return False
    if is_volatile_query(text) and _WEB_FRAGMENT_HINTS.search(norm):
        return True
    return bool(
        re.search(
            r"\b(clima|tiempo|temperatura|weather|pronóstico|pronostico|lluvia|"
            r"noticias?|precio|cotiza|busca|buscar|investiga|google|internet|"
            r"mercado|tendencia|actualidad|creatina|suplemento)\b",
            norm,
        )
    )


def _web_kind_for(text: str) -> str:
    if is_weather_intent(text):
        return "weather"
    if is_news_intent(text):
        return "news"
    return "general"


def resolve_web_search_request(
    user_text: str,
    transcript: list[Utterance],
) -> dict[str, str] | None:
    """Detecta búsqueda web usando el último turno — sin mezclar noticias previas."""
    last = (user_text or "").strip()
    if not last or _normalize(last) in _ACK_ONLY:
        return None

    lines = _user_lines(transcript)
    prev = lines[-2] if len(lines) >= 2 else ""

    if prev and _is_fragment_continuation(last, prev):
        query = f"{prev} {last}".strip()
        intent_source = query
    else:
        query = last
        intent_source = last

    if not _needs_internet_lookup(intent_source):
        return None

    kind = _web_kind_for(intent_source)
    if kind == "news" and not is_news_intent(intent_source):
        kind = "general"

    return {"kind": kind, "query": query}


def web_search_hold_phrase(kind: str) -> str:
    if kind == "weather":
        return "Un momento, señor, consulto el clima."
    if kind == "news":
        return "Un momento, señor, consulto las noticias."
    return "Un momento, señor, busco eso en internet."


def should_respond_to_transcript(
    transcript: list[Utterance],
    *,
    interaction_type: str,
) -> bool:
    """Evita autorespuestas, recordatorios vacíos y turnos parciales muy cortos."""
    if interaction_type == "reminder_required":
        return False

    user_lines = _user_lines(transcript)
    if not user_lines:
        return False

    last = user_lines[-1].strip()
    normalized = _normalize(last)
    if normalized in _ECHO_USER_LINES:
        return False

    if resolve_web_search_request(last, transcript) is not None:
        return True

    words = last.split()
    if len(words) < 2 and len(last) < 12 and not last.rstrip().endswith(("?", ".", "!")):
        return False

    return True


def _is_task_or_info_query(text: str) -> bool:
    """Preguntas reales (clima, noticias, tools) — no son small talk."""
    return _needs_internet_lookup(text) or bool(
        re.search(
            r"\b(publica|publicar|recuerda|memoria|carolina|imagen|genera)\b",
            _normalize(text),
        )
    )


def is_small_talk(text: str) -> bool:
    if _is_task_or_info_query(text):
        return False
    norm = _normalize(text)
    if norm in _SMALL_TALK or norm in _ACK_ONLY:
        return True
    if re.search(r"hola.*(como|cómo)\s+estás?\b", norm):
        return True
    if re.search(r"hola.*\bs[ií]\b", norm) and re.search(r"(como|cómo)\s+estás?\b", norm):
        return True
    if re.search(r"(como|cómo)\s+estás?\s*$", norm) or re.search(r"(como|cómo)\s+estás?\?", norm):
        return True
    if norm.startswith("hola") and len(norm.split()) <= 6:
        return True
    return False


def is_generic_agent_line(text: str) -> bool:
    norm = _normalize(text)
    if norm in {_normalize(line) for line in _GENERIC_AGENT_LINES}:
        return True
    if "operativo" in norm and "servicio" in norm:
        return True
    if norm.startswith("operativo"):
        return True
    if "en qué puedo ayudarle" in norm or "en que puedo ayudarle" in norm:
        return True
    if norm in {"muy bien, señor", "muy bien señor"}:
        return True
    return False


def concise_reply_for_small_talk(user_text: str) -> str:
    norm = _normalize(user_text)
    if re.search(r"(como|cómo)\s+estás?\b", norm) or "qué tal" in norm or "que tal" in norm:
        return "Muy bien, señor. ¿En qué puedo ayudarle?"
    if norm.startswith("hola") or norm in ("buenos días", "buenas tardes", "buenas noches"):
        return "Buenos días, señor. ¿En qué puedo ayudarle?"
    return "¿En qué puedo ayudarle, señor?"
