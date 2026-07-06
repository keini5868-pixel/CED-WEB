"""OAuth Google — Calendar y Gmail (tokens en Supabase)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from urllib.parse import urlencode

import httpx

from app.config import get_settings
from app.services import supabase_db
from app.services.user_id_utils import normalize_user_id

logger = logging.getLogger(__name__)

GoogleService = Literal["calendar", "gmail"]

CALENDAR_SCOPES = (
    "https://www.googleapis.com/auth/calendar.readonly "
    "https://www.googleapis.com/auth/calendar.events"
)
GMAIL_SCOPES = (
    "https://www.googleapis.com/auth/gmail.readonly "
    "https://www.googleapis.com/auth/gmail.send "
    "https://www.googleapis.com/auth/gmail.compose"
)

_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


def _calendar_redirect_uri() -> str:
    settings = get_settings()
    custom = settings.google_calendar_redirect_uri.strip()
    if custom:
        return custom
    return f"{settings.api_public_url.rstrip('/')}/auth/google/calendar/callback"


def _gmail_redirect_uri() -> str:
    settings = get_settings()
    custom = settings.google_gmail_redirect_uri.strip()
    if custom:
        return custom
    return f"{settings.api_public_url.rstrip('/')}/auth/google/gmail/callback"


def _oauth_client_config() -> tuple[str, str]:
    settings = get_settings()
    client_id = settings.google_calendar_client_id.strip()
    client_secret = settings.google_calendar_client_secret.strip()
    if not client_id or not client_secret:
        raise ValueError("Google Calendar OAuth no configurado en Railway.")
    return client_id, client_secret


def oauth_configured() -> bool:
    settings = get_settings()
    return bool(
        settings.google_calendar_client_id.strip()
        and settings.google_calendar_client_secret.strip()
    )


def _oauth_state_secret() -> str:
    settings = get_settings()
    secret = settings.supabase_jwt_secret.strip() or settings.google_calendar_client_secret.strip()
    if not secret:
        raise ValueError("OAuth state secret no configurado.")
    return secret


def build_oauth_state(user_id: str) -> str:
    """State firmado — evita mismatch al volver del callback de Google."""
    from jose import jwt

    uid = normalize_user_id(user_id)
    return jwt.encode({"uid": uid, "v": 1}, _oauth_state_secret(), algorithm="HS256")


def parse_oauth_state(state: str) -> str:
    """Recupera user_id del state (JWT firmado o UUID legacy en vuelo)."""
    from jose import JWTError, jwt

    raw = (state or "").strip()
    if not raw:
        raise ValueError("OAuth state vacío.")
    try:
        return normalize_user_id(raw)
    except ValueError:
        pass
    try:
        payload = jwt.decode(raw, _oauth_state_secret(), algorithms=["HS256"])
        uid = payload.get("uid")
        if not uid:
            raise ValueError("OAuth state sin uid.")
        return normalize_user_id(str(uid))
    except JWTError as exc:
        raise ValueError("OAuth state inválido.") from exc


def ensure_profile_for_oauth(user_id: str) -> None:
    """Garantiza fila en profiles antes del FK de calendar_tokens/gmail_tokens."""
    uid = normalize_user_id(user_id)
    if supabase_db.get_profile(uid):
        return
    try:
        client = supabase_db._client()
        auth_res = client.auth.admin.get_user_by_id(uid)
        user = auth_res.user if hasattr(auth_res, "user") else auth_res
        email = getattr(user, "email", None) or ""
        meta = getattr(user, "user_metadata", None) or {}
        full_name = meta.get("full_name", "") if isinstance(meta, dict) else ""
        client.table("profiles").upsert(
            {
                "id": uid,
                "email": email,
                "full_name": full_name or "",
                "role": "client",
            },
            on_conflict="id",
        ).execute()
        logger.info("[GOOGLE-OAUTH] profile ensured user=%s", uid[:8])
    except Exception:  # noqa: BLE001
        logger.warning("[GOOGLE-OAUTH] profile ensure failed user=%s", uid[:8], exc_info=True)


def build_oauth_url(service: GoogleService, user_id: str) -> str:
    client_id, _ = _oauth_client_config()
    if service == "calendar":
        redirect_uri = _calendar_redirect_uri()
        scopes = CALENDAR_SCOPES
    else:
        redirect_uri = _gmail_redirect_uri()
        scopes = GMAIL_SCOPES
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scopes,
        "access_type": "offline",
        "prompt": "consent",
        "state": build_oauth_state(user_id),
        "include_granted_scopes": "true",
    }
    return f"{_GOOGLE_AUTH_URL}?{urlencode(params)}"


def exchange_code(service: GoogleService, code: str) -> dict[str, Any]:
    client_id, client_secret = _oauth_client_config()
    redirect_uri = _calendar_redirect_uri() if service == "calendar" else _gmail_redirect_uri()
    with httpx.Client(timeout=20.0) as client:
        res = client.post(
            _GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        res.raise_for_status()
        return res.json()


def refresh_access_token(service: GoogleService, refresh_token: str) -> dict[str, Any]:
    client_id, client_secret = _oauth_client_config()
    with httpx.Client(timeout=20.0) as client:
        res = client.post(
            _GOOGLE_TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
        res.raise_for_status()
        return res.json()


def _expires_at_from_token(payload: dict[str, Any]) -> str | None:
    expires_in = payload.get("expires_in")
    if not expires_in:
        return None
    when = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in) - 30)
    return when.isoformat()


def store_tokens(service: GoogleService, user_id: str, payload: dict[str, Any]) -> None:
    uid = normalize_user_id(user_id)
    ensure_profile_for_oauth(uid)
    access = str(payload.get("access_token") or "").strip()
    if not access:
        raise ValueError("Google no devolvió access_token.")
    refresh = payload.get("refresh_token")
    if not refresh:
        existing = (
            supabase_db.get_calendar_tokens(uid)
            if service == "calendar"
            else supabase_db.get_gmail_tokens(uid)
        )
        if existing and existing.get("refresh_token"):
            refresh = existing.get("refresh_token")
    row = {
        "access_token": access,
        "refresh_token": refresh,
        "expires_at": _expires_at_from_token(payload),
    }
    if service == "calendar":
        supabase_db.upsert_calendar_tokens(uid, row)
    else:
        supabase_db.upsert_gmail_tokens(uid, row)
    logger.info("[GOOGLE-OAUTH] tokens stored service=%s user=%s", service, uid[:8])


def get_connection_status(service: GoogleService, user_id: str) -> dict[str, Any]:
    try:
        uid = normalize_user_id(user_id)
    except ValueError:
        return {"connected": False, "service": service}
    row = (
        supabase_db.get_calendar_tokens(uid)
        if service == "calendar"
        else supabase_db.get_gmail_tokens(uid)
    )
    return {"connected": bool(row and row.get("access_token")), "service": service}


def get_valid_access_token(service: GoogleService, user_id: str) -> str:
    try:
        uid = normalize_user_id(user_id)
    except ValueError as exc:
        raise ValueError("not_connected") from exc
    row = (
        supabase_db.get_calendar_tokens(uid)
        if service == "calendar"
        else supabase_db.get_gmail_tokens(uid)
    )
    if not row or not row.get("access_token"):
        raise ValueError("not_connected")

    access = str(row["access_token"])
    expires_raw = row.get("expires_at")
    if expires_raw:
        try:
            expires = datetime.fromisoformat(str(expires_raw).replace("Z", "+00:00"))
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if expires > datetime.now(timezone.utc):
                return access
        except Exception:  # noqa: BLE001
            return access

    refresh = str(row.get("refresh_token") or "").strip()
    if not refresh:
        return access

    try:
        payload = refresh_access_token(service, refresh)
        store_tokens(service, uid, {**payload, "refresh_token": refresh})
        new_access = str(payload.get("access_token") or "").strip()
        if new_access:
            return new_access
    except Exception:  # noqa: BLE001
        logger.warning("[GOOGLE-OAUTH] refresh failed service=%s user=%s", service, user_id[:8])
    return access
