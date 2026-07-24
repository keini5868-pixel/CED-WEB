"""NL parsers for local reminders (shared; not Google Calendar)."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

_WEEKDAYS = {
    "lunes": 0,
    "martes": 1,
    "miercoles": 2,
    "miércoles": 2,
    "jueves": 3,
    "viernes": 4,
    "sabado": 5,
    "sábado": 5,
    "domingo": 6,
}


def _parse_time(text: str, default_hour: int = 9) -> tuple[int, int]:
    # Además de "am/pm" explícito, reconoce los meridianos en español que la
    # gente realmente dice por voz ("a las 5 de la tarde/noche/madrugada/mañana").
    m = re.search(
        r"(?:a\s+las?\s+)?(\d{1,2})(?::(\d{2}))?\s*"
        r"(am|pm|a\.?\s*m\.?|p\.?\s*m\.?|"
        r"de\s+la\s+tarde|de\s+la\s+noche|de\s+la\s+madrugada|de\s+la\s+ma[nñ]ana)?",
        text,
        re.I,
    )
    if not m:
        return default_hour, 0
    hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    meridiem = (m.group(3) or "").lower()
    is_pm = meridiem.startswith("p") or "tarde" in meridiem or "noche" in meridiem
    is_am = (
        meridiem.startswith("a")
        or "madrugada" in meridiem
        or "ma\u00f1ana" in meridiem
        or "manana" in meridiem
    )
    if is_pm and hour < 12:
        hour += 12
    if "noche" in meridiem and hour == 12:
        hour = 0  # "12 de la noche" = medianoche
    if is_am and hour == 12:
        hour = 0
    return max(0, min(hour, 23)), max(0, min(minute, 59))


def _parse_target_day(text: str, tz: ZoneInfo) -> datetime:
    now = datetime.now(tz)
    t = text.lower()
    if re.search(r"\bhoy\b", t):
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if re.search(r"ma[nñ]ana", t):
        return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    for name, weekday in _WEEKDAYS.items():
        if re.search(rf"\b{re.escape(name)}\b", t):
            delta = (weekday - now.weekday()) % 7
            if delta == 0:
                delta = 7
            return (now + timedelta(days=delta)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
    return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


def _extract_title(text: str, *, reminder: bool = False) -> str:
    if reminder:
        m = re.search(
            r"recu[eé]rdame\s+(?:que\s+)?(.+?)(?:\s+(?:ma[nñ]ana|hoy|el\s+|a\s+las|\d{1,2}(?::\d{2})?\s*(?:am|pm))|$)",
            text,
            re.I,
        )
        if m:
            title = m.group(1).strip(" .,")
            if len(title) >= 3:
                return title[:120]
    _TIME_STOP = (
        r"el\s+|ma[nñ]ana|hoy|a\s+las|para\s+(?:el\s+|las\s+|\d)|"
        r"\d{1,2}(?::\d{2})?\s*(?:am|pm)"
    )
    m = re.search(
        r"(?:ag[eé]ndame|guarda(?:me)?|an[oó]ta(?:me)?|apunta(?:me)?|reserva(?:me)?|"
        rf"registra(?:me)?|ponme)\s+(?:una?\s+)?(.+?)(?:\s+(?:{_TIME_STOP})|$)",
        text,
        re.I,
    )
    if m:
        title = m.group(1).strip(" .,")
        if len(title) >= 3:
            return title[:120]
    title_match = re.search(r"cita\s+(?:para|de|sobre)?\s*(.+)$", text, re.I)
    title = (title_match.group(1).strip() if title_match else text.strip())[:120]
    return title if len(title) >= 3 else ("Recordatorio CED" if reminder else "Cita CED")
