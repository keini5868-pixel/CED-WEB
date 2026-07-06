"""OAuth Google Calendar y Gmail."""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse

from app.config import get_settings
from app.deps.auth import require_user_id
from app.services.google_oauth import (
    build_oauth_url,
    exchange_code,
    get_connection_status,
    google_oauth_diagnostics,
    oauth_configured,
    parse_oauth_state,
    resolve_allowed_web_origin,
    store_tokens,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/google", tags=["google"])
auth_router = APIRouter(tags=["google-auth"])


def _redirect_web(query: str, web_origin: str | None = None) -> RedirectResponse:
    web = (web_origin or get_settings().web_public_url).strip().rstrip("/")
    return RedirectResponse(f"{web}/dashboard?{query}")


def _resolve_web_origin(request: Request, web_origin: str | None) -> str | None:
    header_origin = request.headers.get("origin", "").strip()
    if header_origin:
        allowed = resolve_allowed_web_origin(header_origin)
        if allowed:
            return allowed
    referer = request.headers.get("referer", "").strip()
    if referer:
        from urllib.parse import urlparse

        parsed = urlparse(referer)
        if parsed.scheme and parsed.netloc:
            allowed = resolve_allowed_web_origin(f"{parsed.scheme}://{parsed.netloc}")
            if allowed:
                return allowed
    return resolve_allowed_web_origin(web_origin or "")


@router.get("/oauth/diagnostics")
def google_oauth_public_diagnostics() -> dict:
    """Redirect URIs y tablas OAuth — sin secretos."""
    return google_oauth_diagnostics()


@router.get("/calendar/oauth/url")
def calendar_oauth_url(
    request: Request,
    web_origin: str | None = Query(default=None),
    user_id: str = Depends(require_user_id),
) -> dict:
    if not oauth_configured():
        raise HTTPException(status_code=503, detail="Google Calendar OAuth no configurado.")
    origin = _resolve_web_origin(request, web_origin)
    return {"url": build_oauth_url("calendar", user_id, web_origin=origin)}


@router.get("/gmail/oauth/url")
def gmail_oauth_url(
    request: Request,
    web_origin: str | None = Query(default=None),
    user_id: str = Depends(require_user_id),
) -> dict:
    if not oauth_configured():
        raise HTTPException(status_code=503, detail="Google Gmail OAuth no configurado.")
    origin = _resolve_web_origin(request, web_origin)
    return {"url": build_oauth_url("gmail", user_id, web_origin=origin)}


@router.get("/calendar/status")
def calendar_status(user_id: str = Depends(require_user_id)) -> dict:
    return get_connection_status("calendar", user_id)


@router.get("/gmail/status")
def gmail_status(user_id: str = Depends(require_user_id)) -> dict:
    return get_connection_status("gmail", user_id)


@auth_router.get("/auth/google/calendar/login")
def calendar_login(
    request: Request,
    web_origin: str | None = Query(default=None),
    user_id: str = Depends(require_user_id),
) -> RedirectResponse:
    if not oauth_configured():
        return _redirect_web("google_calendar=missing_config")
    origin = _resolve_web_origin(request, web_origin)
    return RedirectResponse(build_oauth_url("calendar", user_id, web_origin=origin))


@auth_router.get("/auth/google/gmail/login")
def gmail_login(
    request: Request,
    web_origin: str | None = Query(default=None),
    user_id: str = Depends(require_user_id),
) -> RedirectResponse:
    if not oauth_configured():
        return _redirect_web("google_gmail=missing_config")
    origin = _resolve_web_origin(request, web_origin)
    return RedirectResponse(build_oauth_url("gmail", user_id, web_origin=origin))


@auth_router.get("/auth/google/calendar/callback")
def calendar_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> RedirectResponse:
    if error or not code or not state:
        logger.warning("[GOOGLE:CALENDAR] callback error=%s", error)
        return _redirect_web("google_calendar=error")
    web_origin: str | None = None
    try:
        user_id, web_origin = parse_oauth_state(state)
        logger.info(
            "[OAUTH CALLBACK] calendar code recibido user=%s web=%s",
            user_id[:8],
            web_origin or "default",
        )
        payload = exchange_code("calendar", code)
        logger.info("[OAUTH CALLBACK] guardando token calendar para user: %s", user_id)
        store_tokens("calendar", user_id, payload)
        logger.info("[OAUTH CALLBACK] token calendar guardado exitosamente user=%s", user_id[:8])
        return _redirect_web("google_calendar=connected", web_origin)
    except ValueError as exc:
        logger.warning("[GOOGLE:CALENDAR] callback rejected: %s", exc)
        return _redirect_web("google_calendar=error", web_origin)
    except httpx.HTTPError:
        logger.exception("[GOOGLE:CALENDAR] token exchange failed")
        return _redirect_web("google_calendar=token_failed", web_origin)
    except RuntimeError as exc:
        logger.error("[GOOGLE:CALENDAR] token persist failed: %s", exc)
        return _redirect_web("google_calendar=token_failed", web_origin)
    except Exception:  # noqa: BLE001
        logger.exception("[GOOGLE:CALENDAR] callback failed")
        return _redirect_web("google_calendar=error", web_origin)


@auth_router.get("/auth/google/gmail/callback")
def gmail_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> RedirectResponse:
    if error or not code or not state:
        logger.warning("[GOOGLE:GMAIL] callback error=%s", error)
        return _redirect_web("google_gmail=error")
    web_origin: str | None = None
    try:
        user_id, web_origin = parse_oauth_state(state)
        logger.info(
            "[OAUTH CALLBACK] gmail code recibido user=%s web=%s",
            user_id[:8],
            web_origin or "default",
        )
        payload = exchange_code("gmail", code)
        logger.info("[OAUTH CALLBACK] guardando token gmail para user: %s", user_id)
        store_tokens("gmail", user_id, payload)
        logger.info("[OAUTH CALLBACK] token gmail guardado exitosamente user=%s", user_id[:8])
        return _redirect_web("google_gmail=connected", web_origin)
    except ValueError as exc:
        logger.warning("[GOOGLE:GMAIL] callback rejected: %s", exc)
        return _redirect_web("google_gmail=error", web_origin)
    except httpx.HTTPError:
        logger.exception("[GOOGLE:GMAIL] token exchange failed")
        return _redirect_web("google_gmail=token_failed", web_origin)
    except RuntimeError as exc:
        logger.error("[GOOGLE:GMAIL] token persist failed: %s", exc)
        return _redirect_web("google_gmail=token_failed", web_origin)
    except Exception:  # noqa: BLE001
        logger.exception("[GOOGLE:GMAIL] callback failed")
        return _redirect_web("google_gmail=error", web_origin)
