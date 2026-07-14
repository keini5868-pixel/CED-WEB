"""Frases habladas para finanzas — montos y fechas en español natural (TTS)."""

from __future__ import annotations

import re
from datetime import date, datetime, time
from typing import Any

_ONES = (
    "cero",
    "un",
    "dos",
    "tres",
    "cuatro",
    "cinco",
    "seis",
    "siete",
    "ocho",
    "nueve",
    "diez",
    "once",
    "doce",
    "trece",
    "catorce",
    "quince",
    "dieciséis",
    "diecisiete",
    "dieciocho",
    "diecinueve",
)
_TENS = (
    "",
    "",
    "veinte",
    "treinta",
    "cuarenta",
    "cincuenta",
    "sesenta",
    "setenta",
    "ochenta",
    "noventa",
)
_HUNDREDS = (
    "",
    "ciento",
    "doscientos",
    "trescientos",
    "cuatrocientos",
    "quinientos",
    "seiscientos",
    "setecientos",
    "ochocientos",
    "novecientos",
)

_WEEKDAYS = (
    "lunes",
    "martes",
    "miércoles",
    "jueves",
    "viernes",
    "sábado",
    "domingo",
)
_MONTHS = (
    "",
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

# "a las 9 de la noche", "9:30 pm", "a las pm" (STT basura)
_DUE_TIME_RE = re.compile(
    r"\b(?:a\s+las?\s+)?"
    r"(?:"
    r"(\d{1,2})(?::(\d{2}))?\s*(?:de\s+la\s+)?"
    r"(ma[nñ]ana|tarde|noche|madrugada)"
    r"|"
    r"(\d{1,2})(?::(\d{2}))?\s*(a\.?\s*m\.?|p\.?\s*m\.?|am|pm)"
    r"|"
    r"(\d{1,2})(?::(\d{2}))\b"  # 21:00 / 9:30 sin am/pm
    r")",
    re.I,
)

_TIME_SCRUB_RE = re.compile(
    r"\b(?:a\s+las?\s+)?"
    r"(?:"
    r"\d{1,2}(?::\d{2})?\s*(?:de\s+la\s+)?(?:ma[nñ]ana|tarde|noche|madrugada)"
    r"|"
    r"\d{1,2}(?::\d{2})?\s*(?:a\.?\s*m\.?|p\.?\s*m\.?|am|pm)"
    r"|"
    r"\d{1,2}:\d{2}"
    r"|"
    r"a\s+las?\s+(?:la\s+)?(?:ma[nñ]ana|tarde|noche|pm|am)"
    r")\b",
    re.I,
)

_DESC_TIME_RE = re.compile(r"(?:^|\b)hora\s+(\d{1,2}:\d{2})\b", re.I)


def _under_100(n: int, *, feminine: bool = False) -> str:
    if n < 20:
        word = _ONES[n]
        if feminine and n == 1:
            return "una"
        return word
    if n < 30:
        if n == 20:
            return "veinte"
        ones = n - 20
        ones_word = "una" if feminine and ones == 1 else _ONES[ones]
        return f"veinti{ones_word}" if ones != 2 else "veintidós"
    tens, ones = divmod(n, 10)
    if ones == 0:
        return _TENS[tens]
    ones_word = "una" if feminine and ones == 1 else _ONES[ones]
    return f"{_TENS[tens]} y {ones_word}"


def _under_1000(n: int, *, feminine: bool = False) -> str:
    if n < 100:
        return _under_100(n, feminine=feminine)
    if n == 100:
        return "cien"
    hundreds, rest = divmod(n, 100)
    head = _HUNDREDS[hundreds]
    if rest == 0:
        return head
    return f"{head} {_under_100(rest, feminine=feminine)}"


def integer_to_spoken_es(n: int, *, feminine: bool = False) -> str:
    """Convierte entero >= 0 a español (hasta cientos de millones)."""
    if n < 0:
        return f"menos {integer_to_spoken_es(-n, feminine=feminine)}"
    if n < 1000:
        return _under_1000(n, feminine=feminine)
    if n < 1_000_000:
        thousands, rest = divmod(n, 1000)
        if thousands == 1:
            head = "mil"
        else:
            head = f"{_under_1000(thousands)} mil"
        if rest == 0:
            return head
        return f"{head} {_under_1000(rest, feminine=feminine)}"
    millions, rest = divmod(n, 1_000_000)
    if millions == 1:
        head = "un millón"
    else:
        head = f"{integer_to_spoken_es(millions)} millones"
    if rest == 0:
        return head
    return f"{head} {integer_to_spoken_es(rest, feminine=feminine)}"


def _currency_label(currency: str, amount: float) -> str:
    cur = (currency or "USD").strip().upper()
    plural = abs(amount) != 1
    if cur in {"USD", "US$", "$"}:
        return "dólares" if plural else "dólar"
    if cur in {"EUR", "EUROS"}:
        return "euros" if plural else "euro"
    if cur in {"DOP", "MXN", "COP", "ARS", "CLP", "PEN", "PESOS"}:
        return "pesos" if plural else "peso"
    return cur


def amount_to_spoken_es(amount: Any, currency: str = "USD") -> str:
    """
    Monto natural para TTS: «mil quinientos dólares», nunca «1 5 0 0».
    """
    try:
        value = float(str(amount).replace(",", "").strip())
    except (TypeError, ValueError):
        return "un monto"
    if value < 0:
        return f"menos {amount_to_spoken_es(-value, currency)}"

    whole = int(value)
    cents = int(round((value - whole) * 100))
    if cents == 100:
        whole += 1
        cents = 0

    label = _currency_label(currency, float(whole) if cents == 0 else value)
    if whole == 0 and cents > 0:
        return f"{integer_to_spoken_es(cents, feminine=True)} centavos"
    spoken = f"{integer_to_spoken_es(whole)} {label}"
    if cents > 0:
        spoken += f" con {integer_to_spoken_es(cents, feminine=True)} centavos"
    return spoken


def parse_due_time(text: str) -> str | None:
    """Extrae hora HH:MM (24h) de frases habladas. None si no hay hora clara."""
    t = (text or "").strip()
    if not t:
        return None
    m = _DUE_TIME_RE.search(t)
    if not m:
        return None

    hour: int | None = None
    minute = 0
    if m.group(1) is not None:
        hour = int(m.group(1))
        minute = int(m.group(2) or 0)
        period = (m.group(3) or "").lower()
        if "noche" in period or "tarde" in period:
            if hour < 12:
                hour += 12
        elif "madrugada" in period or "mañana" in period or "manana" in period:
            if hour == 12:
                hour = 0
    elif m.group(4) is not None:
        hour = int(m.group(4))
        minute = int(m.group(5) or 0)
        mer = re.sub(r"[.\s]", "", (m.group(6) or "").lower())
        if mer.startswith("p") and hour < 12:
            hour += 12
        elif mer.startswith("a") and hour == 12:
            hour = 0
    elif m.group(7) is not None:
        hour = int(m.group(7))
        minute = int(m.group(8) or 0)
    else:
        return None

    if hour is None or not (0 <= hour <= 23) or not (0 <= minute <= 59):
        return None
    return f"{hour:02d}:{minute:02d}"


def scrub_time_phrases(text: str) -> str:
    """Elimina expresiones de hora para no meterlas en categoría."""
    cleaned = _TIME_SCRUB_RE.sub(" ", text or "")
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" .,;")
    return cleaned


def due_time_to_spoken_es(hhmm: str | None) -> str:
    if not hhmm:
        return ""
    try:
        hour_s, minute_s = hhmm.split(":", 1)
        hour = int(hour_s)
        minute = int(minute_s)
    except (TypeError, ValueError):
        return ""
    if hour == 0 and minute == 0:
        return "a medianoche"
    if hour == 12 and minute == 0:
        return "a mediodía"

    if hour < 12:
        period = "de la mañana"
        display = 12 if hour == 0 else hour
    elif hour == 12:
        period = "de la tarde"
        display = 12
    elif hour < 20:
        period = "de la tarde"
        display = hour - 12
    else:
        period = "de la noche"
        display = hour - 12

    hour_word = integer_to_spoken_es(display)
    if minute == 0:
        return f"a las {hour_word} {period}"
    return f"a las {hour_word} y {integer_to_spoken_es(minute, feminine=True)} {period}"


def due_date_to_spoken_es(due_raw: Any, *, due_time: str | None = None) -> str:
    """«el viernes 17 de julio» (+ hora si hay)."""
    d: date | None = None
    if isinstance(due_raw, date) and not isinstance(due_raw, datetime):
        d = due_raw
    elif due_raw:
        try:
            d = datetime.strptime(str(due_raw)[:10], "%Y-%m-%d").date()
        except ValueError:
            return str(due_raw)
    if d is None:
        base = "la fecha indicada"
    else:
        base = f"el {_WEEKDAYS[d.weekday()]} {d.day} de {_MONTHS[d.month]}"

    time_part = due_time_to_spoken_es(due_time)
    if time_part:
        return f"{base} {time_part}"
    return base


def due_time_from_description(description: str | None) -> str | None:
    if not description:
        return None
    m = _DESC_TIME_RE.search(description)
    return m.group(1) if m else None


def embed_due_time_in_description(description: str | None, due_time: str | None) -> str | None:
    """Persiste la hora en description (no hay columna due_time en BD)."""
    base = (description or "").strip()
    if not due_time:
        return base or None
    if _DESC_TIME_RE.search(base):
        return base or None
    prefix = f"hora {due_time}."
    return f"{prefix} {base}".strip() if base else prefix


def format_money_spoken(amount: Any, currency: str = "USD") -> str:
    return amount_to_spoken_es(amount, currency)
