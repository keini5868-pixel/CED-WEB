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
    "https://www.googleapis.com/auth/calendar "
    "https://www.googleapis.com/auth/calendar.events"
)
GMAIL_SCOPES = (
    "https://www.googleapis.com/auth/gmail.readonly "
    "https://www.googleapis.com/auth/gmail.send "
    "https://www.googleapis.com/auth/gmail.compose"
)

_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_TOKENINFO_URL = "https://www.googleapis.com/oauth2/v3/tokeninfo"

CALENDAR_RECONNECT_MSG = (
    "Permisos de Calendar insuficientes. Pulse «Reconectar Calendar», acepte "
    "todos los permisos de Google y confirme en Supabase → Auth → Google que "
    "estén habilitados calendar y calendar.events."
)
CALENDAR_WRITE_SCOPE_MSG = (
    "Falta permiso para crear eventos. Reconecte Calendar y acepte el permiso "
    "de gestión de calendario (calendar.events)."
)
GMAIL_RECONNECT_MSG = (
    "Permisos de Gmail insuficientes. Pulse «Conectar Gmail» de nuevo "
    "y acepte todos los permisos."
)


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
    pairs = _oauth_client_pairs()
    return pairs[0]


def _oauth_client_pairs() -> list[tuple[str, str]]:
    """Clientes OAuth para refresh — Railway y/o Supabase Auth (mismo Google Cloud app)."""
    settings = get_settings()
    seen: set[str] = set()
    pairs: list[tuple[str, str]] = []
    for client_id, client_secret in (
        (
            settings.google_calendar_client_id.strip(),
            settings.google_calendar_client_secret.strip(),
        ),
        (
            settings.google_supabase_oauth_client_id.strip(),
            settings.google_supabase_oauth_client_secret.strip(),
        ),
    ):
        if not client_id or not client_secret or client_id in seen:
            continue
        seen.add(client_id)
        pairs.append((client_id, client_secret))
    if not pairs:
        raise ValueError("Google Calendar OAuth no configurado en Railway.")
    return pairs


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


def build_oauth_state(user_id: str, web_origin: str | None = None) -> str:
    """State firmado — evita mismatch al volver del callback de Google."""
    from jose import jwt

    uid = normalize_user_id(user_id)
    payload: dict[str, str | int] = {"uid": uid, "v": 1}
    allowed_web = resolve_allowed_web_origin(web_origin or "")
    if allowed_web:
        payload["web"] = allowed_web
    return jwt.encode(payload, _oauth_state_secret(), algorithm="HS256")


def resolve_allowed_web_origin(candidate: str) -> str | None:
    """Solo orígenes permitidos (CORS / localhost) — evita open redirect."""
    from urllib.parse import urlparse

    raw = (candidate or "").strip().rstrip("/")
    if not raw:
        return None
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None
    origin = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    if "localhost" in origin or "127.0.0.1" in origin:
        return origin
    allowed = get_settings().cors_origin_list()
    if origin in allowed:
        return origin
    logger.warning("[GOOGLE-OAUTH] web origin not in CORS allowlist: %s", origin)
    return None


def parse_oauth_state(state: str) -> tuple[str, str | None]:
    """Recupera (user_id, web_origin) del state (JWT firmado o UUID legacy)."""
    from jose import JWTError, jwt

    raw = (state or "").strip()
    if not raw:
        raise ValueError("OAuth state vacío.")
    try:
        return normalize_user_id(raw), None
    except ValueError:
        pass
    try:
        payload = jwt.decode(raw, _oauth_state_secret(), algorithms=["HS256"])
        uid = payload.get("uid")
        if not uid:
            raise ValueError("OAuth state sin uid.")
        web_raw = payload.get("web")
        web = (
            resolve_allowed_web_origin(str(web_raw))
            if isinstance(web_raw, str) and web_raw.strip()
            else None
        )
        return normalize_user_id(str(uid)), web
    except JWTError as exc:
        raise ValueError("OAuth state inválido.") from exc


def google_oauth_diagnostics() -> dict[str, Any]:
    """Diagnóstico público OAuth — redirect URIs y tablas (sin secretos)."""
    import os

    settings = get_settings()
    tables_ok: bool | None = None
    tables_error: str | None = None
    try:
        from app.services.supabase_client import get_supabase_admin, service_role_configured

        if service_role_configured():
            get_supabase_admin(require_service_role=True).table("calendar_tokens").select(
                "user_id"
            ).limit(1).execute()
            tables_ok = True
        else:
            tables_ok = False
            tables_error = "SUPABASE_SERVICE_ROLE_KEY missing"
    except Exception as exc:  # noqa: BLE001
        tables_ok = False
        tables_error = str(exc)[:240]

    return {
        "oauth_configured": oauth_configured(),
        "api_public_url": settings.api_public_url.strip() or None,
        "web_public_url": settings.web_public_url.strip() or None,
        "calendar_redirect_uri": _calendar_redirect_uri(),
        "gmail_redirect_uri": _gmail_redirect_uri(),
        "calendar_client_id": "OK" if settings.google_calendar_client_id.strip() else "MISSING",
        "calendar_client_secret": (
            "OK" if settings.google_calendar_client_secret.strip() else "MISSING"
        ),
        "supabase_oauth_client_id": (
            "OK" if settings.google_supabase_oauth_client_id.strip() else "MISSING"
        ),
        "supabase_oauth_client_secret": (
            "OK" if settings.google_supabase_oauth_client_secret.strip() else "MISSING"
        ),
        "calendar_redirect_env": (
            "SET" if settings.google_calendar_redirect_uri.strip() else "AUTO"
        ),
        "gmail_redirect_env": (
            "SET" if settings.google_gmail_redirect_uri.strip() else "AUTO"
        ),
        "oauth_token_storage_ready": tables_error != "SUPABASE_SERVICE_ROLE_KEY missing",
        "oauth_tables_ok": tables_ok,
        "oauth_tables_error": tables_error,
        "railway_public_domain": os.environ.get("RAILWAY_PUBLIC_DOMAIN"),
    }


def ensure_profile_for_oauth(user_id: str) -> None:
    """Garantiza fila en profiles antes del FK de calendar_tokens/gmail_tokens."""
    uid = normalize_user_id(user_id)
    existing = supabase_db.get_profile(uid)
    if existing:
        logger.info("[GOOGLE-OAUTH] profile exists user_id=%s", uid)
        return
    logger.info("[GOOGLE-OAUTH] creating profile user_id=%s", uid)
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
    except Exception as exc:  # noqa: BLE001
        logger.error("[GOOGLE-OAUTH] profile ensure failed user=%s: %s", uid[:8], exc)
        raise ValueError("No se pudo crear perfil para guardar tokens OAuth.") from exc
    if not supabase_db.get_profile(uid):
        raise ValueError("Perfil ausente tras ensure — no se pueden guardar tokens OAuth.")


def build_oauth_url(
    service: GoogleService,
    user_id: str,
    *,
    web_origin: str | None = None,
) -> str:
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
        "state": build_oauth_state(user_id, web_origin),
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
        if res.status_code >= 400:
            logger.error(
                "[GOOGLE-OAUTH] token exchange failed service=%s status=%s "
                "redirect_uri=%s body=%s",
                service,
                res.status_code,
                redirect_uri,
                res.text[:500],
            )
        res.raise_for_status()
        return res.json()


def refresh_access_token(service: GoogleService, refresh_token: str) -> dict[str, Any]:
    last_error: str | None = None
    with httpx.Client(timeout=20.0) as client:
        for client_id, client_secret in _oauth_client_pairs():
            res = client.post(
                _GOOGLE_TOKEN_URL,
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
            )
            if res.status_code < 400:
                return res.json()
            last_error = res.text[:300]
            logger.warning(
                "[GOOGLE-OAUTH] refresh failed service=%s client=%s… status=%s",
                service,
                client_id[:12],
                res.status_code,
            )
    logger.error(
        "[GOOGLE-OAUTH] refresh exhausted service=%s body=%s",
        service,
        last_error or "",
    )
    raise httpx.HTTPStatusError(
        "refresh_failed",
        request=httpx.Request("POST", _GOOGLE_TOKEN_URL),
        response=httpx.Response(400, text=last_error or "refresh_failed"),
    )


def inspect_access_token(access_token: str) -> dict[str, Any]:
    """Metadatos del token (scopes) vía Google tokeninfo."""
    with httpx.Client(timeout=12.0) as client:
        res = client.get(
            _GOOGLE_TOKENINFO_URL,
            params={"access_token": access_token},
        )
        if res.status_code >= 400:
            logger.warning("[GOOGLE-OAUTH] tokeninfo %s: %s", res.status_code, res.text[:200])
            return {}
        return res.json()


def _scope_parts(access_token: str) -> set[str]:
    if not (access_token or "").strip():
        return set()
    scope = str(inspect_access_token(access_token).get("scope") or "")
    return {part.strip() for part in scope.split() if part.strip()}


def _calendar_scope_sets() -> tuple[frozenset[str], frozenset[str]]:
    read_scopes = frozenset(
        {
            "https://www.googleapis.com/auth/calendar",
            "https://www.googleapis.com/auth/calendar.readonly",
            "https://www.googleapis.com/auth/calendar.events",
        }
    )
    write_scopes = frozenset(
        {
            "https://www.googleapis.com/auth/calendar",
            "https://www.googleapis.com/auth/calendar.events",
            "https://www.googleapis.com/auth/calendar.events.owned",
            "https://www.googleapis.com/auth/calendar.app.created",
        }
    )
    return read_scopes, write_scopes


def token_has_calendar_read_scope(access_token: str) -> bool:
    parts = _scope_parts(access_token)
    if not parts:
        return False
    read_scopes, _ = _calendar_scope_sets()
    return bool(parts & read_scopes)


def token_has_calendar_write_scope(access_token: str) -> bool:
    parts = _scope_parts(access_token)
    if not parts:
        return False
    _, write_scopes = _calendar_scope_sets()
    return bool(parts & write_scopes)


def token_has_calendar_scope(access_token: str) -> bool:
    """Guardar token Calendar — requiere lectura y escritura (HUD crea eventos)."""
    return token_has_calendar_read_scope(access_token) and token_has_calendar_write_scope(
        access_token
    )


def token_has_gmail_scope(access_token: str) -> bool:
    scope = str(inspect_access_token(access_token).get("scope") or "")
    return any(
        marker in scope
        for marker in (
            "auth/gmail.readonly",
            "auth/gmail.send",
            "auth/gmail.compose",
            "auth/gmail.modify",
        )
    )


def force_refresh_access_token(service: GoogleService, user_id: str) -> str:
    """Fuerza refresh — útil tras 401/403 de la API de Google."""
    uid = normalize_user_id(user_id)
    row = (
        supabase_db.get_calendar_tokens(uid)
        if service == "calendar"
        else supabase_db.get_gmail_tokens(uid)
    )
    if not row or not row.get("access_token"):
        raise ValueError("not_connected")
    refresh = str(row.get("refresh_token") or "").strip()
    if not refresh:
        raise ValueError("reconnect_required")
    payload = refresh_access_token(service, refresh)
    store_tokens(service, uid, {**payload, "refresh_token": refresh})
    new_access = str(payload.get("access_token") or "").strip()
    if not new_access:
        raise ValueError("reconnect_required")
    return new_access


def _expires_at_from_token(payload: dict[str, Any]) -> str | None:
    expires_in = payload.get("expires_in")
    if not expires_in:
        return None
    when = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in) - 30)
    return when.isoformat()


def store_tokens(service: GoogleService, user_id: str, payload: dict[str, Any]) -> None:
    uid = normalize_user_id(user_id)
    logger.info("[GOOGLE-OAUTH] store_tokens start service=%s user_id=%s", service, uid)
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
            logger.info("[GOOGLE-OAUTH] reutilizando refresh_token existente user=%s", uid)
    row = {
        "access_token": access,
        "refresh_token": refresh,
        "expires_at": _expires_at_from_token(payload),
        "expires_in": payload.get("expires_in"),
    }
    if service == "calendar":
        from app.services.supabase_client import save_calendar_tokens

        saved = save_calendar_tokens(uid, row)
    else:
        from app.services.supabase_client import save_gmail_tokens

        saved = save_gmail_tokens(uid, row)
    logger.info(
        "[GOOGLE-OAUTH] upsert ok service=%s user_id=%s saved_user_id=%s has_token=%s",
        service,
        uid,
        saved.get("user_id"),
        bool(saved.get("access_token")),
    )
    status = get_connection_status(service, uid)
    if not status.get("connected"):
        raise RuntimeError(
            f"Verificación falló: token {service} no legible en Supabase tras guardar "
            f"(user_id={uid})"
        )
    logger.info("[GOOGLE-OAUTH] tokens stored service=%s user_id=%s", service, uid)


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
    if not row or not row.get("access_token"):
        return {"connected": False, "service": service}
    if service == "calendar":
        from app.services.google_calendar_api import probe_calendar_access

        access = _access_token_for_status("calendar", uid, row)
        read_ok = token_has_calendar_read_scope(access)
        write_ok = token_has_calendar_write_scope(access)
        if read_ok and write_ok:
            return {"connected": True, "service": service}
        if probe_calendar_access(access):
            logger.info(
                "[GOOGLE-OAUTH] calendar OK via API probe (tokeninfo vacío) user=%s",
                uid[:8],
            )
            return {"connected": True, "service": service}
        refresh = str(row.get("refresh_token") or "").strip()
        if refresh:
            try:
                payload = refresh_access_token("calendar", refresh)
                access = str(payload.get("access_token") or "").strip()
                if access and probe_calendar_access(access):
                    from app.services.supabase_client import save_calendar_tokens

                    save_calendar_tokens(uid, {**payload, "refresh_token": refresh})
                    logger.info(
                        "[GOOGLE-OAUTH] calendar OK tras refresh+probe user=%s",
                        uid[:8],
                    )
                    return {"connected": True, "service": service}
            except Exception:  # noqa: BLE001
                logger.warning(
                    "[GOOGLE-OAUTH] calendar refresh+probe failed user=%s",
                    uid[:8],
                )
        return {
            "connected": False,
            "service": service,
            "needs_reconnect": True,
            "hint": CALENDAR_RECONNECT_MSG,
        }
    return {"connected": True, "service": service}


def _access_token_for_status(
    service: GoogleService,
    user_id: str,
    row: dict[str, Any],
) -> str:
    """Devuelve access token fresco para validación — sin recursión con store_tokens."""
    access = str(row.get("access_token") or "")
    expires_raw = row.get("expires_at")
    needs_refresh = False
    if expires_raw:
        try:
            expires = datetime.fromisoformat(str(expires_raw).replace("Z", "+00:00"))
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            needs_refresh = expires <= datetime.now(timezone.utc)
        except Exception:  # noqa: BLE001
            needs_refresh = False
    refresh = str(row.get("refresh_token") or "").strip()
    if not needs_refresh or not refresh:
        return access
    try:
        payload = refresh_access_token(service, refresh)
        new_access = str(payload.get("access_token") or "").strip()
        if not new_access:
            return access
        if service == "calendar":
            from app.services.supabase_client import save_calendar_tokens

            save_calendar_tokens(user_id, {**payload, "refresh_token": refresh})
        else:
            from app.services.supabase_client import save_gmail_tokens

            save_gmail_tokens(user_id, {**payload, "refresh_token": refresh})
        return new_access
    except Exception:  # noqa: BLE001
        logger.warning(
            "[GOOGLE-OAUTH] refresh for status failed service=%s user=%s",
            service,
            str(user_id)[:8],
        )
        return access


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
