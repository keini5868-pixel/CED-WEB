"""Comprobaciones de conectividad Supabase y Stripe (Fase 1)."""

from __future__ import annotations

from typing import Any

import httpx
import stripe
from supabase import create_client

from app.config import get_settings
from app.services.gemini_live import create_ephemeral_token


def check_gemini() -> dict[str, Any]:
    settings = get_settings()
    if not settings.google_api_key.strip():
        return {
            "ok": False,
            "error": "missing_google_api_key",
            "hint": "Añade GOOGLE_API_KEY en apps/api/.env y reinicia pnpm dev:api",
        }
    result = create_ephemeral_token()
    if not result.get("ok"):
        return {
            "ok": False,
            "error": result.get("error", "token_failed"),
            "model": settings.gemini_live_model,
        }
    return {
        "ok": True,
        "model": result.get("model"),
        "ephemeral_token": True,
    }


def check_supabase() -> dict[str, Any]:
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        return {"ok": False, "error": "missing_credentials"}

    try:
        client = create_client(
            settings.supabase_url,
            settings.supabase_service_role_key,
        )
        result = (
            client.table("founding_registry")
            .select("slots_used, slots_max")
            .limit(1)
            .execute()
        )
        rows = result.data or []
        if not rows:
            return {
                "ok": False,
                "error": "founding_registry_empty",
                "hint": "Ejecuta 001_initial_schema.sql en Supabase SQL Editor",
            }
        return {"ok": True, "founding_registry": rows[0]}
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        if "founding_registry" in msg or "PGRST205" in msg or "42P01" in msg:
            return {
                "ok": False,
                "error": "schema_not_migrated",
                "hint": "Ejecuta apps/api/migrations/001_initial_schema.sql",
            }
        return {"ok": False, "error": msg[:200]}


def check_stripe() -> dict[str, Any]:
    settings = get_settings()
    if not settings.stripe_secret_key:
        return {"ok": False, "error": "missing_stripe_secret_key"}

    try:
        stripe.api_key = settings.stripe_secret_key
        account = stripe.Account.retrieve()
        return {
            "ok": True,
            "account_id": getattr(account, "id", None),
            "livemode": bool(getattr(account, "livemode", False)),
        }
    except stripe.error.AuthenticationError:
        return {"ok": False, "error": "invalid_stripe_secret_key"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:200]}


def check_supabase_auth() -> dict[str, Any]:
    """Health del proyecto vía REST (anon no requerido)."""
    settings = get_settings()
    if not settings.supabase_url:
        return {"ok": False, "error": "missing_url"}

    try:
        url = f"{settings.supabase_url.rstrip('/')}/auth/v1/health"
        with httpx.Client(timeout=10.0) as client:
            response = client.get(url)
        return {"ok": response.status_code < 500, "status_code": response.status_code}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:200]}


def check_supabase_auth_api_key() -> dict[str, Any]:
    """Comprueba que la API key (service role o anon) pertenece al proyecto."""
    settings = get_settings()
    url = settings.supabase_url.strip().rstrip("/")
    if not url:
        return {"ok": False, "error": "missing_url", "project_ref": None}

    project_ref = url.replace("https://", "").split(".")[0]
    api_key = (
        settings.supabase_service_role_key.strip()
        or settings.supabase_anon_key.strip()
    )
    if not api_key:
        return {
            "ok": False,
            "error": "missing_api_key",
            "project_ref": project_ref,
        }

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(
                f"{url}/auth/v1/user",
                headers={
                    "apikey": api_key,
                    "Authorization": "Bearer invalid.test-token",
                },
            )
        body = response.text
        if response.status_code == 403 and "bad_jwt" in body:
            return {"ok": True, "project_ref": project_ref}
        if response.status_code == 401 and "Invalid API key" in body:
            return {
                "ok": False,
                "error": "invalid_api_key",
                "project_ref": project_ref,
            }
        return {
            "ok": False,
            "error": f"unexpected_status_{response.status_code}",
            "project_ref": project_ref,
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:200], "project_ref": project_ref}
