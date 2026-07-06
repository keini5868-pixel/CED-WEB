"""Recordatorios HUD — almacenamiento y respuestas de voz/chat."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from app.services import supabase_db

try:
    from zoneinfo import ZoneInfo

    _TZ = ZoneInfo("America/New_York")
except Exception:  # noqa: BLE001
    _TZ = timezone(timedelta(hours=-4))


def is_reminder_intent(text: str) -> bool:
    import re

    t = (text or "").strip().lower()
    if len(t) < 8:
        return False
    patterns = (
        r"\b(?:qu[eé]|que)\s+recordatorios?\s+tengo\b",
        r"\b(?:qu[eé]|que)\s+tengo\s+(?:de\s+)?recordatorios?\b",
        r"\b(?:mis\s+)?recordatorios\b",
        r"\brecu[eé]rdame\b",
    )
    return any(re.search(p, t) for p in patterns)


def create_reminder(user_id: str, *, text: str, reminder_date: str, reminder_time: str) -> bool:
    return bool(
        supabase_db.insert_hud_reminder(
            user_id,
            text=text.strip(),
            reminder_date=reminder_date,
            reminder_time=reminder_time or "09:00",
        )
    )


def upcoming_reminders(user_id: str, *, limit: int = 10) -> list[dict]:
    today = datetime.now(_TZ).date()
    items: list[dict] = []
    for row in supabase_db.list_hud_reminders(user_id, limit=limit * 2):
        raw_date = str(row.get("reminder_date") or "")
        raw_time = str(row.get("reminder_time") or "09:00")[:5]
        try:
            when = datetime.fromisoformat(f"{raw_date}T{raw_time}:00").replace(tzinfo=_TZ)
        except ValueError:
            continue
        if when.date() < today - timedelta(days=1):
            continue
        items.append(
            {
                "id": str(row.get("id") or ""),
                "text": str(row.get("text") or ""),
                "date": raw_date,
                "time": raw_time,
                "when": when,
            }
        )
    items.sort(key=lambda item: item["when"])
    return items[:limit]


def format_reminders_spoken(user_id: str) -> str:
    items = upcoming_reminders(user_id)
    if not items:
        return "Señor, no tiene recordatorios pendientes."
    parts = [
        f"{item['date']} a las {item['time']}: {item['text']}"
        for item in items[:6]
    ]
    return "Señor, sus recordatorios: " + "; ".join(parts) + "."


def handle_reminder_create_sync(user_id: str, text: str) -> dict[str, str]:
    from app.modules.calendar_module import (
        ZoneInfo,
        _extract_title,
        _parse_target_day,
        _parse_time,
    )

    tz = ZoneInfo("America/New_York")
    day = _parse_target_day(text, tz)
    hour, minute = _parse_time(text)
    title = _extract_title(text, reminder=True)
    date_str = day.strftime("%Y-%m-%d")
    time_str = f"{hour:02d}:{minute:02d}"
    if create_reminder(
        user_id,
        text=title,
        reminder_date=date_str,
        reminder_time=time_str,
    ):
        return {
            "spoken": (
                f"Señor, guardé su recordatorio «{title}» "
                f"para el {date_str} a las {time_str}."
            )
        }
    return {"spoken": "Señor, no pude guardar el recordatorio."}


def handle_reminder_query_sync(user_id: str, text: str) -> dict[str, str]:
    spoken = format_reminders_spoken(user_id)
    return {"spoken": spoken}
