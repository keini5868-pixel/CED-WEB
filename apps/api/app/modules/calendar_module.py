"""Módulo Google Calendar — consultas y citas por voz."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.modules.base_module import BaseModule
from app.services.google_calendar_api import create_event, list_events, resolve_window
from app.services.google_oauth import get_valid_access_token
from app.services.orchestrator_types import ModuleResult
from app.services.retell_llm_types import Utterance

logger = logging.getLogger(__name__)

CALENDAR_PATTERNS: tuple[str, ...] = (
    r"\b(?:qu[eé]|que)\s+tengo\s+hoy\b",
    r"\b(?:qu[eé]|que)\s+tengo\s+ma[nñ]ana\b",
    r"\b(?:ag[eé]ndame|agendar|programa(?:r|me))\b",
    r"\b(?:qu[eé]|que)\s+eventos\s+tengo\b",
    r"\b(?:esta\s+semana|semana)\b.*\b(?:eventos|citas|calendario)\b",
    r"\b(?:mi\s+)?calendario\b",
    r"\bcita\s+(?:para|el|ma[nñ]ana)\b",
    r"\brecu[eé]rdame\b",
    r"\b(?:qu[eé]|que)\s+recordatorios?\s+tengo\b",
    r"\b(?:qu[eé]|que)\s+tengo\s+(?:de\s+)?recordatorios?\b",
)


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
    m = re.search(r"(?:a\s+las?\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.?\s*m\.?|p\.?\s*m\.?)?", text, re.I)
    if not m:
        return default_hour, 0
    hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    meridiem = (m.group(3) or "").lower()
    if meridiem.startswith("p") and hour < 12:
        hour += 12
    if meridiem.startswith("a") and hour == 12:
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
            return (now + timedelta(days=delta)).replace(hour=0, minute=0, second=0, microsecond=0)
    return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


def _extract_title(text: str, *, reminder: bool = False) -> str:
    if reminder:
        m = re.search(r"recu[eé]rdame\s+(?:que\s+)?(.+?)(?:\s+(?:ma[nñ]ana|hoy|el\s+|a\s+las|\d{1,2}(?::\d{2})?\s*(?:am|pm))|$)", text, re.I)
        if m:
            title = m.group(1).strip(" .,")
            if len(title) >= 3:
                return title[:120]
    m = re.search(r"ag[eé]ndame\s+(.+?)(?:\s+(?:el\s+|para\s+|ma[nñ]ana|hoy|a\s+las|\d{1,2}(?::\d{2})?\s*(?:am|pm))|$)", text, re.I)
    if m:
        title = m.group(1).strip(" .,")
        if len(title) >= 3:
            return title[:120]
    title_match = re.search(r"cita\s+(?:para|de|sobre)?\s*(.+)$", text, re.I)
    title = (title_match.group(1).strip() if title_match else text.strip())[:120]
    return title if len(title) >= 3 else ("Recordatorio CED" if reminder else "Cita CED")


def is_calendar_intent(text: str) -> bool:
    t = (text or "").strip().lower()
    if len(t) < 6:
        return False
    return any(re.search(p, t) for p in CALENDAR_PATTERNS)


def _not_connected_message() -> str:
    return (
        "Señor, aún no tiene Google Calendar conectado. "
        "Use el botón Conectar Google Calendar en configuración de voz."
    )


def handle_calendar_query_sync(user_id: str, text: str) -> dict[str, str]:
    try:
        if re.search(r"recu[eé]rdame", text, re.I):
            return handle_calendar_create_sync(user_id, text, reminder=True)
        if re.search(r"ag[eé]ndame|agendar|programa", text, re.I):
            return handle_calendar_create_sync(user_id, text, reminder=False)
        spoken = _handle_calendar_query(user_id, text)
        return {"spoken": spoken}
    except ValueError as exc:
        if str(exc) == "not_connected":
            return {"spoken": _not_connected_message()}
        return {"spoken": "Señor, no pude acceder a su calendario. Revise la conexión."}
    except Exception:  # noqa: BLE001
        logger.exception("[CALENDAR] sync query failed user=%s", user_id[:8])
        return {"spoken": "Señor, no pude consultar su calendario en este momento."}


def handle_calendar_create_sync(user_id: str, text: str, *, reminder: bool = False) -> dict[str, str]:
    try:
        spoken = _handle_create_appointment(user_id, text, reminder=reminder)
        return {"spoken": spoken}
    except ValueError as exc:
        if str(exc) == "not_connected":
            return {"spoken": _not_connected_message()}
        return {"spoken": "Señor, no pude acceder a su calendario. Revise la conexión."}
    except Exception:  # noqa: BLE001
        logger.exception("[CALENDAR] sync create failed user=%s", user_id[:8])
        return {"spoken": "Señor, no pude agendar en su calendario en este momento."}


def _handle_calendar_query(user_id: str, text: str) -> str:
    access = get_valid_access_token("calendar", user_id)
    t = text.lower()
    if re.search(r"recordatorios?", t):
        from app.services.hud_reminders import format_reminders_spoken

        return format_reminders_spoken(user_id)
    elif re.search(r"ma[nñ]ana", t):
        start, end = resolve_window("tomorrow")
        label = "mañana"
    elif re.search(r"semana|eventos", t):
        start, end = resolve_window("week")
        label = "esta semana"
    elif re.search(r"\bhoy\b", t):
        start, end = resolve_window("today")
        label = "hoy"
    else:
        start, end = resolve_window("today")
        label = "hoy"

    events = list_events(access, time_min=start, time_max=end)
    if not events:
        return f"Señor, no tiene eventos en su calendario para {label}."
    joined = "; ".join(events[:6])
    return f"Señor, para {label}: {joined}."


def _handle_create_appointment(user_id: str, text: str, *, reminder: bool = False) -> str:
    access = get_valid_access_token("calendar", user_id)
    tz = ZoneInfo("America/New_York")
    day = _parse_target_day(text, tz)
    hour, minute = _parse_time(text)
    start = day.replace(hour=hour, minute=minute, second=0, microsecond=0)
    end = start + timedelta(hours=1)
    title = _extract_title(text, reminder=reminder)
    if reminder and not title.lower().startswith("recordatorio"):
        title = f"Recordatorio: {title}"
    create_event(access, summary=title, start=start, end=end)
    when = start.strftime("%A %d/%m a las %I:%M %p").replace(" 0", " ")
    kind = "recordatorio" if reminder else "cita"
    return f"Señor, agendé su {kind} «{title}» para {when}."


class CalendarModule(BaseModule):
    name = "calendar"

    async def activate(
        self,
        transcript: str,
        *,
        user_id: str,
        call_id: str,
        user_text: str = "",
        utterances: list[Utterance] | None = None,
    ) -> ModuleResult:
        self._enter_active()
        return await self._run(user_id, user_text or transcript)

    async def handle_command(
        self,
        transcript: str,
        *,
        user_id: str,
        call_id: str,
        user_text: str = "",
        utterances: list[Utterance] | None = None,
    ) -> ModuleResult:
        if idle := self._guard_passive():
            return idle
        if is_calendar_intent(user_text or transcript):
            return await self._run(user_id, user_text or transcript)
        return self._idle()

    async def _run(self, user_id: str, text: str) -> ModuleResult:
        try:
            if re.search(r"recu[eé]rdame", text, re.I):
                spoken = _handle_create_appointment(user_id, text, reminder=True)
            elif re.search(r"ag[eé]ndame|agendar|programa", text, re.I):
                spoken = _handle_create_appointment(user_id, text)
            else:
                spoken = _handle_calendar_query(user_id, text)
            return ModuleResult(ok=True, spoken=spoken, handles_response=True)
        except ValueError as exc:
            if str(exc) == "not_connected":
                return ModuleResult(ok=False, spoken=_not_connected_message(), handles_response=True)
            return ModuleResult(
                ok=False,
                spoken="Señor, no pude acceder a su calendario. Revise la conexión.",
                handles_response=True,
            )
        except Exception:  # noqa: BLE001
            logger.exception("[CALENDAR] query failed user=%s", user_id[:8])
            return ModuleResult(
                ok=False,
                spoken="Señor, no pude consultar su calendario en este momento.",
                handles_response=True,
            )
