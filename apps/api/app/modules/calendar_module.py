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
    r"\b(?:qu[eé]|que)\s+tengo\s+ma[nñ]ana\b",
    r"\b(?:ag[eé]ndame|agendar|programa(?:r|me))\s+(?:una\s+)?cita\b",
    r"\b(?:qu[eé]|que)\s+eventos\s+tengo\b",
    r"\b(?:esta\s+semana|semana)\b.*\b(?:eventos|citas|calendario)\b",
    r"\b(?:mi\s+)?calendario\b",
    r"\bcita\s+(?:para|el|ma[nñ]ana)\b",
)


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


def _handle_calendar_query(user_id: str, text: str) -> str:
    access = get_valid_access_token("calendar", user_id)
    t = text.lower()
    if re.search(r"ma[nñ]ana", t):
        start, end = resolve_window("tomorrow")
        label = "mañana"
    elif re.search(r"semana|eventos", t):
        start, end = resolve_window("week")
        label = "esta semana"
    else:
        start, end = resolve_window("today")
        label = "hoy"

    events = list_events(access, time_min=start, time_max=end)
    if not events:
        return f"Señor, no tiene eventos en su calendario para {label}."
    joined = "; ".join(events[:6])
    return f"Señor, para {label}: {joined}."


def _handle_create_appointment(user_id: str, text: str) -> str:
    access = get_valid_access_token("calendar", user_id)
    tz = ZoneInfo("America/New_York")
    start = datetime.now(tz) + timedelta(days=1)
    start = start.replace(hour=10, minute=0, second=0, microsecond=0)
    end = start + timedelta(hours=1)
    title_match = re.search(r"cita\s+(?:para|de|sobre)?\s*(.+)$", text, re.I)
    title = (title_match.group(1).strip() if title_match else text.strip())[:120]
    if len(title) < 4:
        title = "Cita CED"
    create_event(access, summary=title, start=start, end=end)
    return f"Señor, agendé «{title}» para mañana a las 10:00."


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
        self._active = True
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
        if is_calendar_intent(user_text or transcript):
            return await self._run(user_id, user_text or transcript)
        return self._idle()

    async def _run(self, user_id: str, text: str) -> ModuleResult:
        try:
            if re.search(r"ag[eé]ndame|agendar|programa", text, re.I):
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
