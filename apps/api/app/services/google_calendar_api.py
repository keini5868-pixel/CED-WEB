"""Google Calendar API v3 — listar y crear eventos."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import httpx

_CALENDAR_BASE = "https://www.googleapis.com/calendar/v3"


def _headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def _format_event(item: dict[str, Any]) -> str:
    start = item.get("start") or {}
    when = start.get("dateTime") or start.get("date") or "?"
    summary = str(item.get("summary") or "Sin título").strip()
    return f"{when}: {summary}"


def list_events(
    access_token: str,
    *,
    time_min: datetime,
    time_max: datetime,
    max_results: int = 8,
) -> list[str]:
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
        res.raise_for_status()
        data = res.json()
    items = data.get("items") or []
    if not items:
        return []
    return [_format_event(item) for item in items]


def create_event(
    access_token: str,
    *,
    summary: str,
    start: datetime,
    end: datetime,
    description: str = "",
) -> dict[str, Any]:
    body = {
        "summary": summary[:200],
        "description": description[:2000],
        "start": {"dateTime": start.isoformat(), "timeZone": str(start.tzinfo or "UTC")},
        "end": {"dateTime": end.isoformat(), "timeZone": str(end.tzinfo or "UTC")},
    }
    with httpx.Client(timeout=20.0) as client:
        res = client.post(
            f"{_CALENDAR_BASE}/calendars/primary/events",
            headers=_headers(access_token),
            json=body,
        )
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
