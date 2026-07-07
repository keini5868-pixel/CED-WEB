"""Diagnóstico completo del sistema — solo super admin."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.config import get_settings
from app.deps.auth import require_super_admin
from app.services.integrations import (
    check_anthropic,
    check_google,
    check_openai,
    check_stripe,
    check_supabase,
    check_supabase_auth,
    check_supabase_auth_api_key,
    check_tavily,
)
from app.build_info import BUILD_VERSION
from app.services.openai_key_utils import openai_api_key_looks_valid

router = APIRouter(prefix="/v1", tags=["diagnostic"])


def _key_configured(value: str) -> bool:
    return bool(value.strip())


@router.get("/diagnostic")
def health_diagnostic(_admin_id: str = Depends(require_super_admin)) -> dict:
    """Estado de servicios, claves y conectividad (solo admin)."""
    settings = get_settings()
    errors: list[str] = []

    api_keys = {
        "anthropic": _key_configured(settings.anthropic_api_key),
        "google": _key_configured(settings.google_api_key),
        "tavily": _key_configured(settings.tavily_api_key),
        "openai": _key_configured(settings.openai_api_key),
        "stripe": _key_configured(settings.stripe_secret_key),
        "supabase_service_role": _key_configured(settings.supabase_service_role_key),
        "supabase_jwt": _key_configured(settings.supabase_jwt_secret),
        "meta_app_id": _key_configured(settings.meta_app_id),
        "meta_app_secret": _key_configured(settings.meta_app_secret),
    }

    supabase_db = check_supabase()
    supabase_auth = check_supabase_auth()
    supabase_keys = check_supabase_auth_api_key()
    stripe_status = check_stripe()
    openai_status = check_openai()
    google_status = check_google()
    anthropic_status = check_anthropic()
    tavily_status = check_tavily()

    services: dict[str, str] = {}
    for name, result in (
        ("supabase_db", supabase_db),
        ("supabase_auth", supabase_auth),
        ("stripe", stripe_status),
        ("openai", openai_status),
        ("google", google_status),
        ("anthropic", anthropic_status),
        ("tavily", tavily_status),
    ):
        if result.get("ok"):
            services[name] = "ok"
        else:
            services[name] = "error"
            err = result.get("error") or result.get("detail") or "unknown"
            errors.append(f"{name}: {err}")

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "environment": settings.app_env,
        "version": BUILD_VERSION,
        "web_public_url": settings.web_public_url,
        "api_public_url": settings.api_public_url,
        "cors_origins": settings.cors_origins,
        "super_admin_configured": bool(settings.super_admin_emails.strip()),
        "api_keys": api_keys,
        "openai_key_looks_valid": openai_api_key_looks_valid(settings.openai_api_key),
        "supabase_keys_valid": supabase_keys.get("keys_valid"),
        "services": services,
        "database": {"connected": supabase_db.get("ok", False)},
        "ready": supabase_db.get("ok")
        and google_status.get("ok")
        and (anthropic_status.get("ok") or google_status.get("ok")),
        "errors": errors,
    }
