"""Reloj autoritativo del servidor — fecha/hora sin alucinaciones del LLM."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence
from zoneinfo import ZoneInfo

MX_TZ = "America/Mexico_City"

_DATETIME_LOOKUP = re.compile(
    r"\b("
    r"qu[eé]\s+d[ií]a\s+es|"
    r"qu[eé]\s+fecha\s+es|"
    r"qu[eé]\s+hora\s+es|"
    r"fecha\s+de\s+hoy|"
    r"d[ií]a\s+de\s+hoy|"
    r"hora\s+actual|"
    r"qu[eé]\s+mes\s+es|"
    r"qu[eé]\s+año\s+es"
    r")\b",
    re.I,
)

_DATETIME_CONFIRM = re.compile(
    r"\b("
    r"est[aá]s?\s+segur[oa]|"
    r"segur[oa]\??|"
    r"de\s+verdad|"
    r"confirmas?|"
    r"est[aá]s?\s+ciert[oa]|"
    r"es\s+cierto"
    r")\b",
    re.I,
)

_SPANISH_DAYS = (
    "lunes",
    "martes",
    "miércoles",
    "jueves",
    "viernes",
    "sábado",
    "domingo",
)
_SPANISH_MONTHS = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)


def mx_now() -> datetime:
    try:
        return datetime.now(ZoneInfo(MX_TZ))
    except Exception:  # noqa: BLE001 — entornos sin tzdata
        return datetime.now(timezone(timedelta(hours=-6)))


def format_datetime_mx(*, for_voice: bool = False) -> str:
    now = mx_now()
    day = _SPANISH_DAYS[now.weekday()]
    month = _SPANISH_MONTHS[now.month - 1]
    if for_voice:
        return (
            f"Hoy es {day} {now.day} de {month} de {now.year}, señor. "
            f"Son las {now.strftime('%H:%M')} hora de Ciudad de México."
        )
    return (
        f"Hoy es {day} {now.day} de {month} de {now.year}, señor. "
        f"Son las {now.strftime('%H:%M')} hora de Ciudad de México."
    )


def clock_context_block() -> str:
    now = mx_now()
    day = _SPANISH_DAYS[now.weekday()]
    month = _SPANISH_MONTHS[now.month - 1]
    return (
        "RELOJ DEL SERVIDOR (Ciudad de México — autoritativo, NO inventes otra fecha u hora): "
        f"{day} {now.day} de {month} de {now.year}, {now.strftime('%H:%M')}."
    )


def is_datetime_query(text: str) -> bool:
    return bool(_DATETIME_LOOKUP.search((text or "").strip()))


def is_datetime_confirmation(text: str) -> bool:
    norm = (text or "").strip()
    if not norm or len(norm) > 120:
        return False
    return bool(_DATETIME_CONFIRM.search(norm))


def _user_lines_from_transcript(transcript: Sequence[Any] | None) -> list[str]:
    lines: list[str] = []
    for item in transcript or []:
        if isinstance(item, dict):
            role = str(item.get("role") or "").lower()
            content = str(item.get("content") or "").strip()
        else:
            role = str(getattr(item, "role", "") or "").lower()
            content = str(getattr(item, "content", "") or "").strip()
        if role == "user" and content:
            lines.append(content)
    return lines


def _prior_datetime_context(
    *,
    history: Sequence[dict[str, Any]] | None = None,
    transcript: Sequence[Any] | None = None,
) -> bool:
    for turn in reversed(list(history or [])[-8:]):
        role = str(turn.get("role") or "").strip().lower()
        content = str(turn.get("content") or "").strip()
        if not content:
            continue
        if role in ("user", "human") and is_datetime_query(content):
            return True
        if role in ("assistant", "model", "claude") and _looks_like_datetime_reply(content):
            return True

    for line in reversed(_user_lines_from_transcript(transcript)[-4:]):
        if is_datetime_query(line):
            return True
    return False


def _looks_like_datetime_reply(content: str) -> bool:
    lowered = content.lower()
    return "hoy es" in lowered and any(month in lowered for month in _SPANISH_MONTHS)


def try_instant_datetime_reply(
    text: str,
    *,
    history: Sequence[dict[str, Any]] | None = None,
    transcript: Sequence[Any] | None = None,
    for_voice: bool = False,
) -> str | None:
    """Respuesta determinística si preguntan fecha/hora o confirman una respuesta previa."""
    if is_datetime_query(text):
        return format_datetime_mx(for_voice=for_voice)
    if is_datetime_confirmation(text) and _prior_datetime_context(
        history=history,
        transcript=transcript,
    ):
        return format_datetime_mx(for_voice=for_voice)
    return None
