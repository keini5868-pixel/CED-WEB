"""OAuth Google Calendar y Gmail."""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse

from app.config import get_settings
from app.deps.auth import require_user_id
from app.services.google_oauth import (
    build_oauth_url,
    exchange_code,
    get_connection_status,
    oauth_configured,
    store_tokens,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/google", tags=["google"])
auth_router = APIRouter(tags=["google-auth"])


def _redirect_web(query: str) -> RedirectResponse:
    web = get_settings().web_public_url.rstrip("/")
    return RedirectResponse(f"{web}/dashboard?{query}")


@router.get("/calendar/oauth/url")
def calendar_oauth_url(user_id: str = Depends(require_user_id)) -> dict:
    if not oauth_configured():
        raise HTTPException(status_code=503, detail="Google Calendar OAuth no configurado.")
    return {"url": build_oauth_url("calendar", user_id)}


@router.get("/gmail/oauth/url")
def gmail_oauth_url(user_id: str = Depends(require_user_id)) -> dict:
    if not oauth_configured():
        raise HTTPException(status_code=503, detail="Google Gmail OAuth no configurado.")
    return {"url": build_oauth_url("gmail", user_id)}


@router.get("/calendar/status")
def calendar_status(user_id: str = Depends(require_user_id)) -> dict:
    return get_connection_status("calendar", user_id)


@router.get("/gmail/status")
def gmail_status(user_id: str = Depends(require_user_id)) -> dict:
    return get_connection_status("gmail", user_id)


@auth_router.get("/auth/google/calendar/login")
def calendar_login(user_id: str = Depends(require_user_id)) -> RedirectResponse:
    if not oauth_configured():
        return _redirect_web("google_calendar=missing_config")
    return RedirectResponse(build_oauth_url("calendar", user_id))


@auth_router.get("/auth/google/gmail/login")
def gmail_login(user_id: str = Depends(require_user_id)) -> RedirectResponse:
    if not oauth_configured():
        return _redirect_web("google_gmail=missing_config")
    return RedirectResponse(build_oauth_url("gmail", user_id))


@auth_router.get("/auth/google/calendar/callback")
def calendar_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> RedirectResponse:
    if error or not code or not state:
        logger.warning("[GOOGLE:CALENDAR] callback error=%s", error)
        return _redirect_web("google_calendar=error")
    try:
        payload = exchange_code("calendar", code)
        store_tokens("calendar", state, payload)
        return _redirect_web("google_calendar=connected")
    except httpx.HTTPError as exc:
        logger.exception("[GOOGLE:CALENDAR] token exchange failed")
        return _redirect_web(f"google_calendar=token_failed")
    except Exception:  # noqa: BLE001
        logger.exception("[GOOGLE:CALENDAR] callback failed")
        return _redirect_web("google_calendar=error")


@auth_router.get("/auth/google/gmail/callback")
def gmail_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> RedirectResponse:
    if error or not code or not state:
        logger.warning("[GOOGLE:GMAIL] callback error=%s", error)
        return _redirect_web("google_gmail=error")
    try:
        payload = exchange_code("gmail", code)
        store_tokens("gmail", state, payload)
        return _redirect_web("google_gmail=connected")
    except httpx.HTTPError:
        logger.exception("[GOOGLE:GMAIL] token exchange failed")
        return _redirect_web("google_gmail=token_failed")
    except Exception:  # noqa: BLE001
        logger.exception("[GOOGLE:GMAIL] callback failed")
        return _redirect_web("google_gmail=error")
