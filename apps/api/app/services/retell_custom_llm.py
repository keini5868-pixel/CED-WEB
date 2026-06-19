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
    }
)

_GENERIC_AGENT_LINES = frozenset(
    {
        "operativo y a su servicio, señor.",
        "operativo y a su servicio señor.",
        "a su servicio, señor.",
    }
)

_WEB_FRAGMENT_HINTS = re.compile(
    r"\b(busca|buscar|buscame|investiga|precio|cotiza|clima|tiempo|temperatura|"
    r"noticia|ultim|dime|dame|cuanto|cuesta|hoy|internet|google|web|mercado|"
    r"tendencia|actualidad|significa|vale)\b",
    re.I,
)


def _normalize(text: str) -> str:
    cleaned = (text or "").strip().lower()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.rstrip(".,!?¿¡")


def _web_kind_for(text: str) -> str:
    if is_weather_intent(text):
        return "weather"
    if is_news_intent(text):
        return "news"
    return "general"


def last_user_text(transcript: list[Utterance]) -> str:
    for utterance in reversed(transcript):
        if utterance.role == "user" and (utterance.content or "").strip():
            return utterance.content.strip()
    return ""


def merged_user_query(transcript: list[Utterance], *, max_lines: int = 5) -> str:
    """Une los últimos turnos del usuario — cubre frases partidas por voz."""
    user_lines = [
        (u.content or "").strip()
        for u in transcript
        if u.role == "user" and (u.content or "").strip()
    ]
    if not user_lines:
        return ""
    return " ".join(user_lines[-max_lines:]).strip()


def _needs_internet_lookup(text: str) -> bool:
    if is_weather_intent(text) or is_news_intent(text) or is_web_research_intent(text):
        return True
    norm = normalize_text(text)
    if len(norm) < 6:
        return False
    if is_volatile_query(text) and _WEB_FRAGMENT_HINTS.search(norm):
        return True
    return bool(
        re.search(
            r"\b(clima|tiempo|temperatura|weather|pronóstico|pronostico|lluvia|"
            r"noticias?|precio|cotiza|busca|buscar|investiga|google|internet|"
            r"mercado|tendencia|actualidad)\b",
            norm,
        )
    )


def resolve_web_search_request(
    user_text: str,
    transcript: list[Utterance],
) -> dict[str, str] | None:
    """Detecta cualquier consulta que requiera internet, incluso frases partidas."""
    merged = merged_user_query(transcript)
    candidates: list[str] = []
    for item in (merged, user_text):
        cleaned = (item or "").strip()
        if cleaned and cleaned not in candidates:
            candidates.append(cleaned)

    for candidate in candidates:
        if _needs_internet_lookup(candidate):
            return {"kind": _web_kind_for(candidate), "query": candidate}

    if merged and _normalize(user_text) != _normalize(merged):
        if _WEB_FRAGMENT_HINTS.search(_normalize(merged)):
            return {"kind": _web_kind_for(merged), "query": merged}
    return None


def web_search_hold_phrase(kind: str) -> str:
    if kind == "weather":
        return "Un momento, señor, consulto el clima."
    if kind == "news":
        return "Un momento, señor, consulto las noticias."
    return "Un momento, señor, busco esa información en internet."


def should_respond_to_transcript(
    transcript: list[Utterance],
    *,
    interaction_type: str,
) -> bool:
    """Evita autorespuestas, recordatorios vacíos y turnos parciales muy cortos."""
    if interaction_type == "reminder_required":
        return False

    user_lines = [
        (u.content or "").strip()
        for u in transcript
        if u.role == "user" and (u.content or "").strip()
    ]
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
    if norm in _SMALL_TALK:
        return True
    if re.search(r"hola.*(como|cómo)\s+estás?\b", norm):
        return True
    if re.search(r"hola.*\bs[ií]\b", norm) and re.search(r"(como|cómo)\s+estás?\b", norm):
        return True
    # Solo "¿cómo estás?" al agente — NO "¿cómo está el clima/tiempo?"
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
