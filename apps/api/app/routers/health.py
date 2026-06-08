"""Health y metadata."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from app.config import get_settings
from app.deps.auth import require_super_admin
from app.rate_limit import limiter
from app.services.integrations import (
    check_gemini,
    check_stripe,
    check_supabase,
    check_supabase_auth,
    check_supabase_auth_api_key,
)
from app.domain.plans import (
    CED_ELITE,
    FOUNDING_MEMBER_MAX_SLOTS,
    PLAN_PRICES_USD,
    PlanId,
    RECHARGE_MAX_USD,
    RECHARGE_MIN_USD,
    RECHARGE_QUICK_AMOUNTS_USD,
    TRIAL_DAYS,
    USAGE_WARNING_PERCENT,
    public_plans_catalog,
    quote_recharge,
)

router = APIRouter(tags=["health"])


@router.get("/health")
@limiter.exempt
def health(_request: Request) -> dict[str, str]:
    settings = get_settings()
    return {
        "status": "ok",
        "service": "castillo-digital-api",
        "env": settings.app_env,
    }


@router.get("/v1/auth/diagnostics")
@limiter.exempt
def auth_diagnostics(_request: Request) -> dict:
    """Diagnóstico público de config Supabase (sin secretos)."""
    settings = get_settings()
    supabase_auth = check_supabase_auth_api_key()
    url = settings.supabase_url.strip()
    project_ref = (
        url.replace("https://", "").split(".")[0] if url else None
    )
    expected_ref = "foscutjtuscqrduugklm"
    return {
        "expected_supabase_project": expected_ref,
        "configured_project_ref": project_ref,
        "project_match": project_ref == expected_ref,
        "has_supabase_url": bool(url),
        "has_service_role_key": bool(settings.supabase_service_role_key.strip()),
        "has_anon_key": bool(settings.supabase_anon_key.strip()),
        "has_jwt_secret": bool(settings.supabase_jwt_secret.strip()),
        "supabase_api_key_valid": supabase_auth.get("ok"),
        "supabase_keys_valid": supabase_auth.get("keys_valid"),
        "supabase_auth_error": supabase_auth.get("error"),
        "super_admin_emails_set": bool(settings.super_admin_emails.strip()),
        "hint": (
            "Si project_match=false o supabase_api_key_valid=false, "
            "corrige variables en Railway servicio CED-WEB y redeploy."
        ),
    }


@router.get("/v1/meta")
def meta() -> dict:
    """Metadatos públicos — producto único + recargas flexibles."""
    settings = get_settings()
    supabase_auth = check_supabase_auth_api_key()
    return {
        "app": "ced-web",
        "product": "CED",
        "phase": 7,
        "web_url": settings.web_public_url,
        "supabase_project_ref": supabase_auth.get("project_ref"),
        "supabase_auth_api_ok": supabase_auth.get("ok"),
        "supabase_auth_error": supabase_auth.get("error"),
        "trial_days": TRIAL_DAYS,
        "usage_warning_percent": USAGE_WARNING_PERCENT,
        "plans": public_plans_catalog(),
        "founding": {
            "max_slots": FOUNDING_MEMBER_MAX_SLOTS,
            "price_usd_month": PLAN_PRICES_USD[PlanId.FOUNDING.value],
            "price_locked_for_life": True,
        },
        "features_elite": {
            "gemini_minutes_per_day": CED_ELITE.gemini_minutes_per_day,
            "ai_images_per_month": CED_ELITE.ai_images_per_month,
            "voice_enabled": CED_ELITE.voice_enabled,
            "camera_enabled": CED_ELITE.camera_enabled,
            "meta_social_enabled": CED_ELITE.meta_social_enabled,
        },
        "recharge": {
            "model": "flexible_amount",
            "margin_keini_percent": 40,
            "client_usage_share_percent": 60,
            "min_usd": RECHARGE_MIN_USD,
            "max_usd": RECHARGE_MAX_USD,
            "quick_amounts_usd": list(RECHARGE_QUICK_AMOUNTS_USD),
            "balance_never_expires": True,
            "gemini_cost_per_hour_usd": 1.5,
            "example_quotes": {
                str(amount): quote_recharge(amount)
                for amount in RECHARGE_QUICK_AMOUNTS_USD
            },
        },
    }


@router.get("/v1/integrations")
def integrations_status(
    _admin_id: str = Depends(require_super_admin),
) -> dict:
    """Estado de integraciones — solo super admin."""
    supabase_db = check_supabase()
    supabase_auth = check_supabase_auth()
    stripe_status = check_stripe()
    gemini_status = check_gemini()
    return {
        "phase": 1,
        "supabase_db": supabase_db,
        "supabase_auth": supabase_auth,
        "stripe": stripe_status,
        "gemini": gemini_status,
        "ready": supabase_db.get("ok")
        and stripe_status.get("ok")
        and gemini_status.get("ok"),
    }


@router.get("/v1/recharge/quote")
def recharge_quote(amount_usd: float = Query(..., ge=5, le=500)) -> dict:
    """Cotización en vivo para monto personalizado de recarga."""
    return quote_recharge(amount_usd)
