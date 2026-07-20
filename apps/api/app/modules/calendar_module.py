"""Módulo Google Calendar — consultas y citas por voz."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from app.modules.base_module import BaseModule
from app.services.google_calendar_api import create_event, list_events, resolve_window
from app.services.google_oauth import force_refresh_access_token, get_valid_access_token
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
    # Además de "am/pm" explícito, reconoce los meridianos en español que la
    # gente realmente dice por voz ("a las 5 de la tarde/noche/madrugada/mañana").
    # Antes solo se detectaba am/pm literal — "5 de la tarde" caía sin meridiano
    # y se guardaba como 5:00 a.m. en vez de 5:00 p.m.
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
    is_am = meridiem.startswith("a") or "madrugada" in meridiem or "ma\u00f1ana" in meridiem or "manana" in meridiem
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
            return (now + timedelta(days=delta)).replace(hour=0, minute=0, second=0, microsecond=0)
    return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


def _extract_title(text: str, *, reminder: bool = False) -> str:
    if reminder:
        m = re.search(r"recu[eé]rdame\s+(?:que\s+)?(.+?)(?:\s+(?:ma[nñ]ana|hoy|el\s+|a\s+las|\d{1,2}(?::\d{2})?\s*(?:am|pm))|$)", text, re.I)
        if m:
            title = m.group(1).strip(" .,")
            if len(title) >= 3:
                return title[:120]
    # "para" es ambiguo: "reunión para las 3pm" (hora) vs "llamada para Rafael" (persona).
    # Solo se corta el título en "para" si le sigue algo con pinta de hora/día — si no,
    # se asume que introduce a la persona y se conserva como parte del título.
    _TIME_STOP = r"el\s+|ma[nñ]ana|hoy|a\s+las|para\s+(?:el\s+|las\s+|\d)|\d{1,2}(?::\d{2})?\s*(?:am|pm)"
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


def is_calendar_intent(text: str) -> bool:
    t = (text or "").strip().lower()
    if len(t) < 6:
        return False
    # «hazme un PDF que diga … cita el lunes …» no es agenda.
    from app.services.chat_intents import is_creative_artifact_intent

    if is_creative_artifact_intent(text):
        return False
    return any(re.search(p, t) for p in CALENDAR_PATTERNS)


def _not_connected_message() -> str:
    return (
        "Señor, aún no tiene Google Calendar conectado. "
        "Use el botón Conectar Google Calendar en configuración de voz."
    )


def _calendar_api_call(user_id: str, fn):
    """Ejecuta fn(access) con refresh automático ante 401/403 — igual que Gmail."""
    access = get_valid_access_token("calendar", user_id)
    try:
        return fn(access)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code not in (401, 403):
            raise
        logger.info("[CALENDAR] token refresh retry user=%s status=%s", user_id[:8], exc.response.status_code)
        access = force_refresh_access_token("calendar", user_id)
        return fn(access)


def _resolve_calendar_windows(text: str) -> list[tuple[datetime, datetime, str]]:
    """Ventanas de consulta — soporta hoy + mañana en la misma pregunta."""
    t = (text or "").lower()
    has_hoy = bool(re.search(r"\bhoy\b", t))
    has_manana = bool(re.search(r"ma[nñ]ana", t))
    has_semana = bool(re.search(r"\bsemana\b", t))

    if has_hoy and has_manana:
        s1, e1 = resolve_window("today")
        s2, e2 = resolve_window("tomorrow")
        return [(s1, e1, "hoy"), (s2, e2, "mañana")]
    if has_manana:
        start, end = resolve_window("tomorrow")
        return [(start, end, "mañana")]
    if has_semana:
        start, end = resolve_window("week")
        return [(start, end, "esta semana")]
    if has_hoy:
        start, end = resolve_window("today")
        return [(start, end, "hoy")]
    start, end = resolve_window("today")
    return [(start, end, "hoy")]


def handle_calendar_read_sync(user_id: str, text: str) -> dict[str, str]:
    """Consulta calendario — si piden agendar, redirige al flujo con confirmación."""
    if re.search(r"ag[eé]ndame|agendar|programa|recu[eé]rdame", text or "", re.I):
        return {
            "spoken": (
                "Señor, para agendar use confirmación explícita: "
                "diga por ejemplo «agéndame reunión mañana a las 3» "
                "y luego confirme con «sí»."
            ),
        }
    try:
        spoken = _handle_calendar_query(user_id, text)
        return {"spoken": spoken}
    except ValueError as exc:
        if str(exc) == "not_connected":
            return {"spoken": _not_connected_message()}
        return {"spoken": "Señor, no pude acceder a su calendario. Revise la conexión."}
    except Exception:  # noqa: BLE001
        logger.exception("[CALENDAR] read sync failed user=%s", user_id[:8])
        return {"spoken": "Señor, no pude consultar su calendario en este momento."}


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
    t = text.lower()
    if re.search(r"recordatorios?", t):
        from app.services.hud_reminders import format_reminders_spoken

        return format_reminders_spoken(user_id)

    windows = _resolve_calendar_windows(text)

    def _fetch(access: str) -> str:
        sections: list[str] = []
        for start, end, label in windows:
            events = list_events(access, time_min=start, time_max=end)
            if events:
                joined = "; ".join(events[:6])
                sections.append(f"para {label}: {joined}")
            else:
                sections.append(f"para {label} no tiene eventos")
        if not sections:
            return "Señor, no tiene eventos en su calendario."
        return f"Señor, {'. '.join(sections)}."

    return _calendar_api_call(user_id, _fetch)


def _handle_create_appointment(user_id: str, text: str, *, reminder: bool = False) -> str:
    tz = ZoneInfo("America/New_York")
    day = _parse_target_day(text, tz)
    hour, minute = _parse_time(text)
    start = day.replace(hour=hour, minute=minute, second=0, microsecond=0)
    end = start + timedelta(hours=1)
    title = _extract_title(text, reminder=reminder)
    if reminder and not title.lower().startswith("recordatorio"):
        title = f"Recordatorio: {title}"

    def _create(access: str) -> str:
        create_event(access, summary=title, start=start, end=end)
        when = start.strftime("%A %d/%m a las %I:%M %p").replace(" 0", " ")
        kind = "recordatorio" if reminder else "cita"
        return f"Señor, agendé su {kind} «{title}» para {when}."

    return _calendar_api_call(user_id, _create)


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
