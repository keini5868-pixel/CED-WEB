"""HUD — carrusel izquierdo y health detallado."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.deps.auth import require_user_id
from app.services.hud_carousel import build_carousel_snapshot
from app.services.hud_health import build_detailed_health
from app.services.hud_life import build_life_dashboard, build_life_dashboard_fallback

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["hud"])


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
async def hud_life(user_id: str = Depends(require_user_id)) -> dict:
    """Dashboard LIFE — clima, calendario, gmail, aire y polen."""
    try:
        return build_life_dashboard(user_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("[LIFE] error: %s", exc)
        return build_life_dashboard_fallback(user_id)


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
    from app.services.google_calendar_api import create_event
    from app.services.google_oauth import get_valid_access_token

    try:
        token = get_valid_access_token("calendar", user_id)
        from datetime import timedelta

        start = datetime.fromisoformat(f"{body.date}T{body.time or '09:00'}:00")
        try:
            from zoneinfo import ZoneInfo

            start = start.replace(tzinfo=ZoneInfo("America/New_York"))
        except Exception:  # noqa: BLE001
            start = start.replace(tzinfo=timezone.utc)
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
        return {"ok": True}
    except ValueError as exc:
        if str(exc) == "not_connected":
            raise HTTPException(status_code=401, detail="Calendar no conectado.") from exc
        raise HTTPException(status_code=400, detail="Fecha u hora inválida.") from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("[HUD] calendar event failed")
        raise HTTPException(status_code=502, detail="No se pudo crear el evento.") from exc


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
