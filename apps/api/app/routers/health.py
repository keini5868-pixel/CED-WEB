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


@router.get("/v1/meta")
def meta() -> dict:
    """Metadatos públicos — producto único + recargas flexibles."""
    settings = get_settings()
    return {
        "app": "ced-web",
        "product": "CED Élite",
        "phase": 1,
        "web_url": settings.web_public_url,
        "trial_days": TRIAL_DAYS,
        "usage_warning_percent": USAGE_WARNING_PERCENT,
        "founding": {
            "max_slots": FOUNDING_MEMBER_MAX_SLOTS,
            "price_usd_month": PLAN_PRICES_USD[PlanId.ELITE_FOUNDING],
            "price_locked_for_life": True,
            "certificate_pdf": True,
        },
        "launch": {
            "price_usd_month": PLAN_PRICES_USD[PlanId.ELITE_REGULAR],
            "from_slot": FOUNDING_MEMBER_MAX_SLOTS + 1,
        },
        "features": {
            "gemini_minutes_per_day": CED_ELITE.gemini_minutes_per_day,
            "video_allowed": CED_ELITE.video_allowed,
            "claude_text_unlimited": CED_ELITE.claude_text_unlimited,
            "ai_images_per_month": CED_ELITE.ai_images_per_month,
            "tts_elevenlabs": CED_ELITE.tts_elevenlabs,
            "whisper_transcription": CED_ELITE.whisper_transcription,
            "memory_unlimited": CED_ELITE.memory_unlimited,
            "folders_unlimited": CED_ELITE.folders_unlimited,
            "pdfs_unlimited": CED_ELITE.pdfs_unlimited,
            "hud_panels_live": CED_ELITE.hud_panels_live,
            "pwa_mobile": CED_ELITE.pwa_mobile,
            "priority_support": CED_ELITE.priority_support,
            "early_access_features": CED_ELITE.early_access_features,
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
