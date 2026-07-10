"""Google Calendar API v3 — listar y crear eventos."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import httpx

logger = logging.getLogger(__name__)

_CALENDAR_BASE = "https://www.googleapis.com/calendar/v3"
_DEFAULT_TZ = "America/New_York"
_DAYS_ES = (
    "Lunes",
    "Martes",
    "Miércoles",
    "Jueves",
    "Viernes",
    "Sábado",
    "Domingo",
)
_MONTHS_ES = (
    "Ene",
    "Feb",
    "Mar",
    "Abr",
    "May",
    "Jun",
    "Jul",
    "Ago",
    "Sep",
    "Oct",
    "Nov",
    "Dic",
)


def _headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def probe_calendar_access(access_token: str) -> bool:
    """Comprueba acceso real a Calendar — más fiable que tokeninfo en tokens refrescados."""
    token = (access_token or "").strip()
    if not token:
        return False
    try:
        with httpx.Client(timeout=12.0) as client:
            res = client.get(
                f"{_CALENDAR_BASE}/calendars/primary",
                headers=_headers(token),
                params={"fields": "id,summary"},
            )
            if res.status_code == 200:
                return True
            logger.warning(
                "[CALENDAR] probe status=%s body=%s",
                res.status_code,
                res.text[:180],
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[CALENDAR] probe failed: %s", exc)
    return False


def _event_time_payload(dt: datetime, tz_name: str = _DEFAULT_TZ) -> dict[str, str]:
    try:
        tz = ZoneInfo(tz_name)
    except Exception:  # noqa: BLE001
        tz = timezone.utc
        tz_name = "UTC"
    local = dt.astimezone(tz) if dt.tzinfo else dt.replace(tzinfo=tz)
    return {
        "dateTime": local.strftime("%Y-%m-%dT%H:%M:%S"),
        "timeZone": tz_name,
    }


def _friendly_calendar_error(exc: Exception) -> tuple[str, bool]:
    from app.services.google_oauth import CALENDAR_RECONNECT_MSG

    if isinstance(exc, httpx.HTTPStatusError):
        if exc.response.status_code in (401, 403):
            return CALENDAR_RECONNECT_MSG, True
    text = str(exc)
    if "403" in text or "401" in text:
        return CALENDAR_RECONNECT_MSG, True
    return "No se pudo acceder a Calendar. Reintente en unos segundos.", False


def _parse_event_start(start: dict[str, Any], tz_name: str = "America/New_York") -> datetime | None:
    raw = start.get("dateTime") or start.get("date")
    if not raw:
        return None
    try:
        if "T" in str(raw):
            dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        else:
            try:
                tz = ZoneInfo(tz_name)
            except Exception:  # noqa: BLE001
                tz = timezone(timedelta(hours=-4))
            dt = datetime.fromisoformat(str(raw)).replace(tzinfo=tz)
        return dt
    except Exception:  # noqa: BLE001
        return None


def _format_event_display(item: dict[str, Any], *, tz_name: str = "America/New_York") -> str:
    start = item.get("start") or {}
    dt = _parse_event_start(start, tz_name)
    summary = str(item.get("summary") or "Sin título").strip()
    if not dt:
        return summary
    try:
        tz = ZoneInfo(tz_name)
    except Exception:  # noqa: BLE001
        tz = timezone(timedelta(hours=-4))
    local = dt.astimezone(tz)
    now = datetime.now(tz)
    if local.date() == now.date():
        time_str = local.strftime("%I:%M %p").lstrip("0")
        return f"Hoy {time_str} — {summary}"
    day = _DAYS_ES[local.weekday()]
    month = _MONTHS_ES[local.month - 1]
    time_str = local.strftime("%I:%M %p").lstrip("0")
    return f"{day} {local.day} {month} — {summary} {time_str}"


def _format_event_structured(
    item: dict[str, Any],
    *,
    tz_name: str = "America/New_York",
) -> dict[str, Any]:
    start = item.get("start") or {}
    dt = _parse_event_start(start, tz_name)
    raw_dt = start.get("dateTime") or start.get("date") or ""
    try:
        tz = ZoneInfo(tz_name)
        now = datetime.now(tz)
        is_today = bool(dt and dt.astimezone(tz).date() == now.date())
    except Exception:  # noqa: BLE001
        is_today = False
    return {
        "id": str(item.get("id") or ""),
        "title": str(item.get("summary") or "Sin título").strip(),
        "datetime": str(raw_dt),
        "location": str(item.get("location") or "").strip(),
        "display": _format_event_display(item, tz_name=tz_name),
        "is_today": is_today,
    }


def list_events_structured(
    access_token: str,
    *,
    time_min: datetime,
    time_max: datetime,
    max_results: int = 10,
    tz_name: str = "America/New_York",
) -> list[dict[str, Any]]:
    params = {
        "timeMin": time_min.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "timeMax": time_max.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "singleEvents": "true",
        "orderBy": "startTime",
        "maxResults": max_results,
    }
    with httpx.Client(timeout=20.0) as client:
        res = client.get(
            f"{_CALENDAR_BASE}/calendars/primary/events",
            headers=_headers(access_token),
            params=params,
        )
        if res.status_code >= 400:
            logger.error(
                "[CALENDAR] API %s: %s",
                res.status_code,
                res.text[:240],
            )
        res.raise_for_status()
        data = res.json()
    items = data.get("items") or []
    return [_format_event_structured(item, tz_name=tz_name) for item in items]


def list_events(
    access_token: str,
    *,
    time_min: datetime,
    time_max: datetime,
    max_results: int = 8,
) -> list[str]:
    structured = list_events_structured(
        access_token,
        time_min=time_min,
        time_max=time_max,
        max_results=max_results,
    )
    if not structured:
        return []
    return [e["display"] for e in structured]


def get_calendar_events(user_id: str) -> dict[str, Any]:
    """Eventos Calendar para HUD — hoy y próximos 7 días."""
    from app.services.google_oauth import (
        force_refresh_access_token,
        get_connection_status,
        get_valid_access_token,
    )

    if not get_connection_status("calendar", user_id).get("connected"):
        return {"connected": False, "events": [], "today_events": [], "week_events": [], "count": 0}

    try:
        token = get_valid_access_token("calendar", user_id)
        start_today, end_today = resolve_window("today")
        start_week, end_week = resolve_window("week")

        def _load_events(access: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
            today = list_events_structured(
                access, time_min=start_today, time_max=end_today, max_results=8
            )
            week = list_events_structured(
                access, time_min=start_week, time_max=end_week, max_results=10
            )
            return today, week

        try:
            today_events, week_events = _load_events(token)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in (401, 403):
                raise
            token = force_refresh_access_token("calendar", user_id)
            today_events, week_events = _load_events(token)

        today_ids = {e.get("id") for e in today_events}
        upcoming = [e for e in week_events if e.get("id") not in today_ids]
        return {
            "connected": True,
            "events": week_events,
            "today_events": today_events,
            "week_events": upcoming,
            "count": len(week_events),
        }
    except ValueError as exc:
        if str(exc) in ("not_connected", "reconnect_required"):
            msg, needs = _friendly_calendar_error(exc)
            return {
                "connected": True,
                "events": [],
                "today_events": [],
                "week_events": [],
                "count": 0,
                "error": msg,
                "needs_reconnect": needs or str(exc) == "reconnect_required",
            }
        raise
    except httpx.HTTPStatusError as exc:
        logger.error("[CALENDAR] HTTP %s: %s", exc.response.status_code, exc.response.text[:200])
        msg, needs = _friendly_calendar_error(exc)
        return {
            "connected": True,
            "events": [],
            "today_events": [],
            "week_events": [],
            "count": 0,
            "error": msg,
            "needs_reconnect": needs,
        }
    except Exception as exc:  # noqa: BLE001
        logger.error("[CALENDAR] error: %s", exc)
        msg, needs = _friendly_calendar_error(exc)
        return {
            "connected": True,
            "events": [],
            "today_events": [],
            "week_events": [],
            "count": 0,
            "error": msg,
            "needs_reconnect": needs,
        }


def create_event(
    access_token: str,
    *,
    summary: str,
    start: datetime,
    end: datetime,
    description: str = "",
    tz_name: str = _DEFAULT_TZ,
) -> dict[str, Any]:
    body = {
        "summary": summary[:200],
        "description": description[:2000],
        "start": _event_time_payload(start, tz_name),
        "end": _event_time_payload(end, tz_name),
    }
    with httpx.Client(timeout=20.0) as client:
        res = client.post(
            f"{_CALENDAR_BASE}/calendars/primary/events",
            headers=_headers(access_token),
            json=body,
        )
        if res.status_code >= 400:
            logger.error("[CALENDAR] create %s: %s", res.status_code, res.text[:240])
        res.raise_for_status()
        return res.json()


def resolve_window(kind: str, *, tz_name: str = "America/New_York") -> tuple[datetime, datetime]:
    try:
        tz = ZoneInfo(tz_name)
    except Exception:  # noqa: BLE001
        tz = timezone(timedelta(hours=-4))
    now = datetime.now(tz)
    if kind == "tomorrow":
        start = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        return start, end
    if kind == "week":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=7)
        return start, end
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start, end
