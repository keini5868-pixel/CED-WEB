"""HUD — carrusel izquierdo y health detallado."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.deps.auth import require_user_id
from app.services.hud_carousel import build_carousel_snapshot
from app.services.hud_health import build_detailed_health
from app.services.hud_life import (
    build_life_connections,
    build_life_dashboard,
    build_life_dashboard_fallback,
    is_weather_cache_expired,
    update_weather_cache,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["hud"])


def _parse_hud_event_datetime(date_raw: str, time_raw: str) -> datetime:
    """Acepta YYYY-MM-DD o DD/MM/YYYY."""
    from zoneinfo import ZoneInfo

    date_str = (date_raw or "").strip()
    time_str = (time_raw or "09:00").strip()
    if "/" in date_str:
        parts = date_str.split("/")
        if len(parts) == 3:
            day, month, year = parts[0].zfill(2), parts[1].zfill(2), parts[2]
            date_str = f"{year}-{month}-{day}"
    if len(time_str) == 5 and time_str.count(":") == 1:
        time_str = f"{time_str}:00"
    elif time_str.count(":") == 1:
        h, m = time_str.split(":", 1)
        time_str = f"{int(h):02d}:{m}:00"
    try:
        start = datetime.fromisoformat(f"{date_str}T{time_str}")
    except ValueError as exc:
        raise ValueError("invalid_datetime") from exc
    try:
        return start.replace(tzinfo=ZoneInfo("America/New_York"))
    except Exception:  # noqa: BLE001
        return start.replace(tzinfo=timezone.utc)


@router.get("/hud/carousel")
async def hud_carousel(user_id: str = Depends(require_user_id)) -> dict:
    """Snapshot de las 7 tarjetas del carrusel CASTILLO."""
    try:
        return build_carousel_snapshot(user_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("[CAROUSEL] error: %s", exc)
        return {
            "cards": [],
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "health": {"ok": False},
            "prospection_mode": False,
            "error": "carousel_unavailable",
        }


@router.get("/health/detailed")
async def health_detailed(_user_id: str = Depends(require_user_id)) -> dict:
    """Health agregado SaaS — tarjeta SYSTEM."""
    return build_detailed_health()


@router.get("/hud/life")
async def hud_life(
    background_tasks: BackgroundTasks,
    user_id: str = Depends(require_user_id),
) -> dict:
    """Dashboard LIFE — clima, calendario, gmail, aire y polen."""
    try:
        snapshot = build_life_dashboard(user_id)
        if is_weather_cache_expired(user_id):
            background_tasks.add_task(update_weather_cache, user_id)
        return snapshot
    except Exception as exc:  # noqa: BLE001
        logger.exception("[LIFE] error: %s", exc)
        return build_life_dashboard_fallback(user_id)


@router.get("/hud/connections")
async def hud_connections(user_id: str = Depends(require_user_id)) -> dict:
    """Calendar + Gmail — rápido, sin búsquedas web."""
    try:
        return build_life_connections(user_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("[LIFE] connections error: %s", exc)
        fb = build_life_dashboard_fallback(user_id)
        return {
            "updated_at": fb["updated_at"],
            "calendar": fb["calendar"],
            "gmail": fb["gmail"],
        }


class CalendarEventBody(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    date: str = Field(description="YYYY-MM-DD")
    time: str = Field(default="09:00", description="HH:MM")
    reminder_minutes: int | None = Field(default=None, ge=0, le=10_080)


class GmailSendBody(BaseModel):
    to: str = Field(min_length=3, max_length=200)
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=8000)


@router.post("/hud/calendar/event")
async def hud_create_calendar_event(
    body: CalendarEventBody,
    user_id: str = Depends(require_user_id),
) -> dict:
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_create_calendar_event_sync, user_id, body),
            timeout=25.0,
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail="Calendar tardó demasiado. Reintenta en unos segundos.",
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("[HUD] calendar event failed")
        raise HTTPException(status_code=502, detail="No se pudo crear el evento.") from exc


def _create_calendar_event_sync(user_id: str, body: CalendarEventBody) -> dict:
    from app.services.google_calendar_api import create_event
    from app.services.google_oauth import (
        CALENDAR_RECONNECT_MSG,
        force_refresh_access_token,
        get_valid_access_token,
    )

    import httpx

    def _create_with_token(token: str) -> None:
        from datetime import timedelta

        start = _parse_hud_event_datetime(body.date, body.time or "09:00")
        end = start + timedelta(hours=1)
        create_event(
            token,
            summary=body.title,
            start=start,
            end=end,
            description=(
                f"Recordatorio CED ({body.reminder_minutes} min antes)"
                if body.reminder_minutes
                else "Evento creado desde CED HUD"
            ),
        )

    try:
        token = get_valid_access_token("calendar", user_id)
        try:
            _create_with_token(token)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in (401, 403):
                raise
            token = force_refresh_access_token("calendar", user_id)
            _create_with_token(token)
        return {"ok": True}
    except ValueError as exc:
        if str(exc) == "not_connected":
            raise HTTPException(status_code=401, detail="Calendar no conectado.") from exc
        if str(exc) == "reconnect_required":
            raise HTTPException(status_code=403, detail=CALENDAR_RECONNECT_MSG) from exc
        if str(exc) == "invalid_datetime":
            raise HTTPException(
                status_code=400,
                detail="Fecha u hora inválida. Use formato AAAA-MM-DD.",
            ) from exc
        raise HTTPException(status_code=400, detail="Fecha u hora inválida.") from exc
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (401, 403):
            raise HTTPException(status_code=403, detail=CALENDAR_RECONNECT_MSG) from exc
        logger.exception("[HUD] calendar event HTTP error")
        raise HTTPException(status_code=502, detail="No se pudo crear el evento.") from exc


@router.get("/hud/gmail/messages")
async def hud_gmail_messages(
    category: str = Query(default="primary"),
    user_id: str = Depends(require_user_id),
) -> dict:
    from app.services.google_gmail_api import get_gmail_emails

    allowed = {"primary", "promotions", "social", "updates", "forums"}
    cat = category if category in allowed else "primary"
    return get_gmail_emails(user_id, cat)  # type: ignore[arg-type]


@router.get("/hud/calendar/events")
async def hud_calendar_events(user_id: str = Depends(require_user_id)) -> dict:
    from app.services.google_calendar_api import get_calendar_events

    return get_calendar_events(user_id)


@router.post("/hud/gmail/send")
async def hud_send_gmail(body: GmailSendBody, user_id: str = Depends(require_user_id)) -> dict:
    from app.services.google_gmail_api import send_message
    from app.services.google_oauth import get_valid_access_token

    try:
        token = get_valid_access_token("gmail", user_id)
        send_message(token, to=body.to, subject=body.subject, body=body.body)
        return {"ok": True}
    except ValueError as exc:
        if str(exc) == "not_connected":
            raise HTTPException(status_code=401, detail="Gmail no conectado.") from exc
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("[HUD] gmail send failed")
        raise HTTPException(status_code=502, detail="No se pudo enviar el email.") from exc


class ReminderBody(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    date: str = Field(description="YYYY-MM-DD")
    time: str = Field(default="09:00", description="HH:MM")


@router.get("/hud/reminders")
async def hud_list_reminders(user_id: str = Depends(require_user_id)) -> dict:
    from app.services.hud_reminders import upcoming_reminders

    items = upcoming_reminders(user_id, limit=20)
    return {
        "reminders": [
            {
                "id": item["id"],
                "text": item["text"],
                "date": item["date"],
                "time": item["time"],
            }
            for item in items
        ]
    }


@router.post("/hud/reminders")
async def hud_create_reminder(
    body: ReminderBody,
    user_id: str = Depends(require_user_id),
) -> dict:
    from app.services.hud_reminders import create_reminder

    ok = create_reminder(
        user_id,
        text=body.text.strip(),
        reminder_date=body.date,
        reminder_time=body.time or "09:00",
    )
    if not ok:
        raise HTTPException(status_code=502, detail="No se pudo guardar el recordatorio.")
    return {"ok": True}
