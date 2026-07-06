"""Clientes Supabase — anon vs service_role (admin)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)

_admin_client: Any | None = None


def service_role_configured() -> bool:
    settings = get_settings()
    return bool(settings.supabase_url.strip() and settings.supabase_service_role_key.strip())


def get_supabase_admin(*, require_service_role: bool = False):
    """Cliente service_role — obligatorio para calendar_tokens/gmail_tokens (RLS deny-all)."""
    global _admin_client
    settings = get_settings()
    url = settings.supabase_url.strip()
    service_key = settings.supabase_service_role_key.strip()
    anon_key = settings.supabase_anon_key.strip()

    if not url:
        raise RuntimeError("SUPABASE_URL no configurada")

    from supabase import create_client

    if service_key:
        if _admin_client is None:
            _admin_client = create_client(url, service_key)
        return _admin_client

    if require_service_role:
        raise RuntimeError(
            "SUPABASE_SERVICE_ROLE_KEY requerida — calendar_tokens/gmail_tokens "
            "tienen RLS deny-all; anon no puede insertar."
        )

    logger.error(
        "[SUPABASE] SUPABASE_SERVICE_ROLE_KEY no configurada — "
        "calendar_tokens/gmail_tokens fallarán por RLS"
    )
    if anon_key:
        return create_client(url, anon_key)
    raise RuntimeError("Supabase no configurado (falta service_role y anon key)")


def _verify_token_row(table: str, user_id: str) -> None:
    from app.services.user_id_utils import normalize_user_id

    uid = normalize_user_id(user_id)
    verify = (
        get_supabase_admin(require_service_role=True)
        .table(table)
        .select("user_id, access_token, updated_at")
        .eq("user_id", uid)
        .limit(1)
        .execute()
    )
    rows = verify.data or []
    logger.info(
        "[OAUTH CALLBACK] verify %s user_id=%s rows=%s",
        table,
        uid,
        len(rows),
    )
    if not rows or not rows[0].get("access_token"):
        raise RuntimeError(
            f"{table}: fila no encontrada tras upsert para user_id={uid}"
        )


def save_calendar_tokens(user_id: str, tokens: dict[str, Any]) -> dict[str, Any]:
    from app.services.user_id_utils import normalize_user_id

    uid = normalize_user_id(user_id)
    if not service_role_configured():
        raise RuntimeError(
            "SUPABASE_SERVICE_ROLE_KEY ausente — no se puede guardar calendar_tokens"
        )
    logger.info("[CALENDAR CALLBACK] guardando token para user_id=%s", uid)
    try:
        expires_at = tokens.get("expires_at")
        if not expires_at and tokens.get("expires_in"):
            expires_at = (
                datetime.now(timezone.utc) + timedelta(seconds=int(tokens["expires_in"]))
            ).isoformat()

        data: dict[str, Any] = {
            "user_id": uid,
            "access_token": tokens["access_token"],
            "expires_at": expires_at,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if tokens.get("refresh_token"):
            data["refresh_token"] = tokens["refresh_token"]

        logger.info(
            "[CALENDAR CALLBACK] upsert keys=%s has_refresh=%s",
            list(data.keys()),
            bool(data.get("refresh_token")),
        )
        result = (
            get_supabase_admin(require_service_role=True)
            .table("calendar_tokens")
            .upsert(data, on_conflict="user_id")
            .select("user_id, access_token, updated_at")
            .execute()
        )
        rows = result.data or []
        logger.info("[CALENDAR CALLBACK] upsert response rows=%s", len(rows))
        saved = rows[0] if rows else None
        if not saved or not saved.get("access_token"):
            _verify_token_row("calendar_tokens", uid)
            saved = saved or {"user_id": uid, "access_token": data["access_token"]}
        else:
            _verify_token_row("calendar_tokens", uid)
        logger.info("[CALENDAR CALLBACK] token guardado exitosamente user_id=%s", uid)
        return saved
    except Exception as exc:
        logger.error(
            "[CALENDAR CALLBACK] ERROR user_id=%s %s: %s",
            uid,
            type(exc).__name__,
            exc,
        )
        raise


def save_gmail_tokens(user_id: str, tokens: dict[str, Any]) -> dict[str, Any]:
    from app.services.user_id_utils import normalize_user_id

    uid = normalize_user_id(user_id)
    if not service_role_configured():
        raise RuntimeError(
            "SUPABASE_SERVICE_ROLE_KEY ausente — no se puede guardar gmail_tokens"
        )
    logger.info("[GMAIL CALLBACK] guardando token para user_id=%s", uid)
    try:
        expires_at = tokens.get("expires_at")
        if not expires_at and tokens.get("expires_in"):
            expires_at = (
                datetime.now(timezone.utc) + timedelta(seconds=int(tokens["expires_in"]))
            ).isoformat()

        data: dict[str, Any] = {
            "user_id": uid,
            "access_token": tokens["access_token"],
            "expires_at": expires_at,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if tokens.get("refresh_token"):
            data["refresh_token"] = tokens["refresh_token"]

        logger.info(
            "[GMAIL CALLBACK] upsert keys=%s has_refresh=%s",
            list(data.keys()),
            bool(data.get("refresh_token")),
        )
        result = (
            get_supabase_admin(require_service_role=True)
            .table("gmail_tokens")
            .upsert(data, on_conflict="user_id")
            .select("user_id, access_token, updated_at")
            .execute()
        )
        rows = result.data or []
        logger.info("[GMAIL CALLBACK] upsert response rows=%s", len(rows))
        saved = rows[0] if rows else None
        if not saved or not saved.get("access_token"):
            _verify_token_row("gmail_tokens", uid)
            saved = saved or {"user_id": uid, "access_token": data["access_token"]}
        else:
            _verify_token_row("gmail_tokens", uid)
        logger.info("[GMAIL CALLBACK] token guardado exitosamente user_id=%s", uid)
        return saved
    except Exception as exc:
        logger.error(
            "[GMAIL CALLBACK] ERROR user_id=%s %s: %s",
            uid,
            type(exc).__name__,
            exc,
        )
        raise
