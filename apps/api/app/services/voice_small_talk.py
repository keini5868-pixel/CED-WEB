"""Respuestas de voz instantáneas para charla casual — sin esperar Ollama."""

from __future__ import annotations

import random
import re

from app.services.retell_custom_llm import _normalize, is_small_talk

_HOW_ARE_YOU_REPLIES: tuple[str, ...] = (
    "Muy bien, señor, gracias por preguntar. ¿En qué puedo asistirle hoy?",
    "Operativo y listo, señor. Cuénteme qué necesita.",
    "Todo en orden por aquí, señor. ¿Qué le gustaría hacer?",
)

_HELLO_REPLIES: tuple[str, ...] = (
    "Hola, señor. Estoy aquí. ¿Qué necesita?",
    "Hola, señor. Dígame en qué le ayudo.",
)

_WHATS_UP_REPLIES: tuple[str, ...] = (
    "Todo bien, señor. ¿Qué tenemos para hoy?",
    "Listo para lo que necesite, señor.",
)

_TIME_GREETINGS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bbuenos\s+d[ií]as\b", re.I), "Buenos días, señor. ¿En qué le asisto?"),
    (re.compile(r"\bbuenas\s+tardes\b", re.I), "Buenas tardes, señor. ¿Qué necesita?"),
    (re.compile(r"\bbuenas\s+noches\b", re.I), "Buenas noches, señor. ¿En qué le ayudo?"),
)


def try_instant_small_talk_voice_reply(text: str) -> str | None:
    """Frase corta sin LLM para saludos y small talk en voz."""
    cleaned = (text or "").strip()
    if not cleaned:
        return None

    norm = _normalize(cleaned)
    if not is_small_talk(cleaned) and not re.search(r"como\s+estas?\b", norm):
        return None

    if re.search(r"como\s+estas?\b", norm) or norm in {
        "como estas",
        "hola como estas",
    }:
        return random.choice(_HOW_ARE_YOU_REPLIES)

    for pattern, reply in _TIME_GREETINGS:
        if pattern.search(norm):
            return reply

    if norm in {"qué tal", "que tal"}:
        return random.choice(_WHATS_UP_REPLIES)

    if norm.startswith("hola") or norm == "hola":
        return random.choice(_HELLO_REPLIES)

    if norm in {"okay", "ok", "sí", "si", "vale", "gracias"}:
        return "De acuerdo, señor. ¿Seguimos?"

    return random.choice(_HOW_ARE_YOU_REPLIES)
