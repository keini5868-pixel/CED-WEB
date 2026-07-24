"""HUD — carrusel izquierdo y health detallado."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from app.deps.auth import require_user_id
from app.services.async_sync import run_sync
from app.services.hud_carousel import build_carousel_snapshot
from app.services.hud_health import build_detailed_health
from app.services.hud_life import (
    build_life_dashboard,
    build_life_dashboard_fallback,
    is_weather_cache_expired,
    update_weather_cache,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["hud"])


@router.get("/hud/carousel")
async def hud_carousel(user_id: str = Depends(require_user_id)) -> dict:
    """Snapshot de las 7 tarjetas del carrusel CASTILLO."""
    try:
        return await run_sync(build_carousel_snapshot, user_id)
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
    return await run_sync(build_detailed_health)


@router.get("/hud/life")
async def hud_life(
    background_tasks: BackgroundTasks,
    user_id: str = Depends(require_user_id),
) -> dict:
    """Dashboard LIFE — clima, aire y polen."""
    try:
        snapshot = await run_sync(build_life_dashboard, user_id)
        if is_weather_cache_expired(user_id):
            background_tasks.add_task(update_weather_cache, user_id)
        return snapshot
    except Exception as exc:  # noqa: BLE001
        logger.exception("[LIFE] error: %s", exc)
        return await run_sync(build_life_dashboard_fallback, user_id)


class ReminderBody(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    date: str = Field(description="YYYY-MM-DD")
    time: str = Field(default="09:00", description="HH:MM")


@router.get("/hud/reminders")
async def hud_list_reminders(user_id: str = Depends(require_user_id)) -> dict:
    from app.services.hud_reminders import upcoming_reminders

    items = await run_sync(upcoming_reminders, user_id, limit=20)
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

    ok = await run_sync(
        create_reminder,
        user_id,
        text=body.text.strip(),
        reminder_date=body.date,
        reminder_time=body.time or "09:00",
    )
    if not ok:
        raise HTTPException(status_code=502, detail="No se pudo guardar el recordatorio.")
    return {"ok": True}
