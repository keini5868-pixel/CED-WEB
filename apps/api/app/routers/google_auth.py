"""OAuth Google Calendar y Gmail."""

from __future__ import annotations

import logging
import traceback

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse

from app.config import get_settings
from app.deps.auth import require_user_id
from app.services.google_oauth import (
    GoogleService,
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


def _run_oauth_callback(
    service: GoogleService,
    *,
    code: str | None,
    state: str | None,
    error: str | None,
) -> RedirectResponse:
    label = "CALENDAR" if service == "calendar" else "GMAIL"
    connected_q = f"google_{service}=connected"
    error_q = f"google_{service}=error"
    token_failed_q = f"google_{service}=token_failed"
    web_origin: str | None = None

    if error or not code or not state:
        logger.warning(
            "[%s CALLBACK] abortado error=%s code=%s state=%s",
            label,
            error,
            "present" if code else "missing",
            "present" if state else "missing",
        )
        return _redirect_web(error_q)

    code_preview = f"{code[:10]}..." if len(code) > 10 else code
    state_preview = f"{state[:24]}..." if len(state) > 24 else state
    logger.info(
        "[%s CALLBACK] Iniciado code=%s state=%s",
        label,
        code_preview,
        state_preview,
    )

    try:
        logger.info("[%s CALLBACK] Parseando state...", label)
        user_id, web_origin = parse_oauth_state(state)
        logger.info("[%s CALLBACK] user_id=%s web_origin=%s", label, user_id, web_origin or "default")

        logger.info("[%s CALLBACK] Intercambiando code por tokens...", label)
        payload = exchange_code(service, code)
        has_access = bool(str(payload.get("access_token") or "").strip())
        has_refresh = bool(str(payload.get("refresh_token") or "").strip())
        logger.info(
            "[%s CALLBACK] Tokens recibidos access_token=%s refresh_token=%s expires_in=%s",
            label,
            has_access,
            has_refresh,
            payload.get("expires_in"),
        )

        logger.info("[%s CALLBACK] Guardando tokens en Supabase user_id=%s...", label, user_id)
        store_tokens(service, user_id, payload)

        status = get_connection_status(service, user_id)
        logger.info(
            "[%s CALLBACK] Verificación post-guardado connected=%s user_id=%s",
            label,
            status.get("connected"),
            user_id,
        )
        if not status.get("connected"):
            raise RuntimeError(
                f"Token {service} no legible en Supabase tras guardar (user_id={user_id})"
            )

        logger.info("[%s CALLBACK] Tokens guardados exitosamente user_id=%s", label, user_id)
        return _redirect_web(connected_q, web_origin)

    except ValueError as exc:
        logger.warning("[%s CALLBACK] ERROR ValueError: %s", label, exc)
        logger.warning("[%s CALLBACK] TRACEBACK:\n%s", label, traceback.format_exc())
        return _redirect_web(error_q, web_origin)
    except httpx.HTTPError as exc:
        logger.error("[%s CALLBACK] ERROR HTTP token exchange: %s", label, exc)
        logger.error("[%s CALLBACK] TRACEBACK:\n%s", label, traceback.format_exc())
        return _redirect_web(token_failed_q, web_origin)
    except RuntimeError as exc:
        logger.error("[%s CALLBACK] ERROR persistencia: %s", label, exc)
        logger.error("[%s CALLBACK] TRACEBACK:\n%s", label, traceback.format_exc())
        return _redirect_web(token_failed_q, web_origin)
    except Exception as exc:  # noqa: BLE001
        logger.error("[%s CALLBACK] ERROR %s: %s", label, type(exc).__name__, exc)
        logger.error("[%s CALLBACK] TRACEBACK:\n%s", label, traceback.format_exc())
        return _redirect_web(error_q, web_origin)


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
    return _run_oauth_callback("calendar", code=code, state=state, error=error)


@auth_router.get("/auth/google/gmail/callback")
def gmail_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> RedirectResponse:
    return _run_oauth_callback("gmail", code=code, state=state, error=error)
