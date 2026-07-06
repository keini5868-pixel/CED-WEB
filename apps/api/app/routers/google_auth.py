"""Google Calendar y Gmail — tokens vía Supabase Auth provider_token."""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.deps.auth import require_user_id
from app.services.google_oauth import (
    CALENDAR_RECONNECT_MSG,
    CALENDAR_WRITE_SCOPE_MSG,
    GMAIL_RECONNECT_MSG,
    get_connection_status,
    google_oauth_diagnostics,
    store_tokens,
    token_has_calendar_read_scope,
    token_has_calendar_write_scope,
    token_has_gmail_scope,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/google", tags=["google"])


class SaveGoogleTokenBody(BaseModel):
    type: Literal["calendar", "gmail"]
    provider_token: str = Field(min_length=10)
    provider_refresh_token: str | None = None


@router.get("/oauth/diagnostics")
def google_oauth_public_diagnostics() -> dict:
    """Tablas OAuth y configuración — sin secretos."""
    return google_oauth_diagnostics()


@router.post("/save-token")
def save_google_token(
    body: SaveGoogleTokenBody,
    user_id: str = Depends(require_user_id),
) -> dict:
    label = body.type.upper()
    logger.info(
        "[%s SAVE] user_id=%s token_len=%d refresh=%s",
        label,
        user_id[:8],
        len(body.provider_token),
        bool(body.provider_refresh_token),
    )
    if body.type == "calendar":
        if not token_has_calendar_read_scope(body.provider_token):
            raise HTTPException(
                status_code=400,
                detail=CALENDAR_RECONNECT_MSG,
            )
        if not token_has_calendar_write_scope(body.provider_token):
            raise HTTPException(
                status_code=400,
                detail=CALENDAR_WRITE_SCOPE_MSG,
            )
    elif body.type == "gmail" and not token_has_gmail_scope(body.provider_token):
        raise HTTPException(
            status_code=400,
            detail=GMAIL_RECONNECT_MSG,
        )
    try:
        store_tokens(
            body.type,
            user_id,
            {
                "access_token": body.provider_token,
                "refresh_token": body.provider_refresh_token,
                "expires_in": 3600,
            },
        )
    except Exception as exc:
        logger.error("[%s SAVE] ERROR: %s", label, exc)
        raise HTTPException(
            status_code=500,
            detail="No se pudo guardar el token.",
        ) from exc

    status = get_connection_status(body.type, user_id)
    if not status.get("connected"):
        logger.error(
            "[%s SAVE] Token no legible tras upsert user_id=%s",
            label,
            user_id,
        )
        raise HTTPException(
            status_code=500,
            detail="Token no verificado en Supabase.",
        )
    return {"ok": True, **status}


@router.get("/calendar/status")
def calendar_status(user_id: str = Depends(require_user_id)) -> dict:
    return get_connection_status("calendar", user_id)


@router.get("/gmail/status")
def gmail_status(user_id: str = Depends(require_user_id)) -> dict:
    return get_connection_status("gmail", user_id)
