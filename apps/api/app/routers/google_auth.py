"""Google Calendar y Gmail — tokens vía Supabase Auth provider_token."""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from app.config import get_settings
from app.deps.auth import require_user_id
from app.services.google_oauth import (
    CALENDAR_RECONNECT_MSG,
    CALENDAR_WRITE_SCOPE_MSG,
    GMAIL_RECONNECT_MSG,
    GMAIL_SEND_SCOPE_MSG,
    build_oauth_url,
    exchange_code,
    get_connection_status,
    google_oauth_diagnostics,
    oauth_configured,
    parse_oauth_state,
    resolve_allowed_web_origin,
    store_tokens,
    token_has_calendar_read_scope,
    token_has_calendar_write_scope,
    token_has_gmail_scope,
    token_has_gmail_send_scope,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/google", tags=["google"])
callback_router = APIRouter(tags=["google-oauth-callback"])


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
    elif body.type == "gmail":
        if not token_has_gmail_scope(body.provider_token):
            raise HTTPException(
                status_code=400,
                detail=GMAIL_RECONNECT_MSG,
            )
        if not token_has_gmail_send_scope(body.provider_token):
            raise HTTPException(
                status_code=400,
                detail=GMAIL_SEND_SCOPE_MSG,
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


@router.get("/calendar/oauth-url")
def calendar_oauth_url(
    request: Request,
    user_id: str = Depends(require_user_id),
) -> dict:
    """URL OAuth directa (Railway) — scopes calendar completos, sin depender de Supabase Auth."""
    if not oauth_configured():
        raise HTTPException(
            status_code=503,
            detail="Google Calendar OAuth no configurado en el servidor.",
        )
    origin = resolve_allowed_web_origin(request.headers.get("origin") or "")
    settings = get_settings()
    web_origin = origin or settings.web_public_url.strip() or None
    return {"url": build_oauth_url("calendar", user_id, web_origin=web_origin)}


@callback_router.get("/auth/google/calendar/callback")
def calendar_oauth_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Callback público de Google OAuth — intercambia code y guarda tokens Calendar."""
    settings = get_settings()
    fallback_web = settings.web_public_url.rstrip("/") or "https://cedweb-production.up.railway.app"
    if error or not code or not state:
        logger.warning("[GOOGLE-OAUTH] calendar callback error=%s code=%s", error, bool(code))
        return RedirectResponse(f"{fallback_web}/dashboard?calendar=error")
    try:
        user_id, web_origin = parse_oauth_state(state)
        payload = exchange_code("calendar", code)
        access = str(payload.get("access_token") or "")
        if not token_has_calendar_read_scope(access):
            target = (web_origin or fallback_web).rstrip("/")
            return RedirectResponse(f"{target}/dashboard?calendar=scope_read")
        if not token_has_calendar_write_scope(access):
            from app.services.google_calendar_api import probe_calendar_access

            if not probe_calendar_access(access):
                target = (web_origin or fallback_web).rstrip("/")
                return RedirectResponse(f"{target}/dashboard?calendar=scope_write")
        store_tokens("calendar", user_id, payload)
        target = (web_origin or fallback_web).rstrip("/")
        return RedirectResponse(f"{target}/dashboard?calendar=connected")
    except Exception as exc:  # noqa: BLE001
        logger.exception("[GOOGLE-OAUTH] calendar callback failed: %s", exc)
        return RedirectResponse(f"{fallback_web}/dashboard?calendar=error")


@router.get("/gmail/status")
def gmail_status(user_id: str = Depends(require_user_id)) -> dict:
    return get_connection_status("gmail", user_id)


@router.get("/gmail/oauth-url")
def gmail_oauth_url(
    request: Request,
    user_id: str = Depends(require_user_id),
) -> dict:
    """URL OAuth directa (Railway) — scopes gmail.send incluidos, sin depender de Supabase Auth."""
    if not oauth_configured():
        raise HTTPException(
            status_code=503,
            detail="Google Gmail OAuth no configurado en el servidor.",
        )
    origin = resolve_allowed_web_origin(request.headers.get("origin") or "")
    settings = get_settings()
    web_origin = origin or settings.web_public_url.strip() or None
    return {"url": build_oauth_url("gmail", user_id, web_origin=web_origin)}


@callback_router.get("/auth/google/gmail/callback")
def gmail_oauth_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Callback público de Google OAuth — intercambia code y guarda tokens Gmail."""
    settings = get_settings()
    fallback_web = settings.web_public_url.rstrip("/") or "https://cedweb-production.up.railway.app"
    if error or not code or not state:
        logger.warning("[GOOGLE-OAUTH] gmail callback error=%s code=%s", error, bool(code))
        return RedirectResponse(f"{fallback_web}/dashboard?gmail=error")
    try:
        user_id, web_origin = parse_oauth_state(state)
        payload = exchange_code("gmail", code)
        access = str(payload.get("access_token") or "")
        if not token_has_gmail_scope(access):
            target = (web_origin or fallback_web).rstrip("/")
            return RedirectResponse(f"{target}/dashboard?gmail=scope_read")
        if not token_has_gmail_send_scope(access):
            target = (web_origin or fallback_web).rstrip("/")
            return RedirectResponse(f"{target}/dashboard?gmail=scope_send")
        store_tokens("gmail", user_id, payload)
        target = (web_origin or fallback_web).rstrip("/")
        return RedirectResponse(f"{target}/dashboard?gmail=connected")
    except Exception as exc:  # noqa: BLE001
        logger.exception("[GOOGLE-OAUTH] gmail callback failed: %s", exc)
        return RedirectResponse(f"{fallback_web}/dashboard?gmail=error")
