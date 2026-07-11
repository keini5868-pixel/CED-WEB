"""Health y metadata."""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, Query, Request

from app.build_info import BUILD_TIMESTAMP, BUILD_VERSION
from app.config import get_settings
from app.deps.auth import require_super_admin
from app.domain.openai_voice_prompt import voice_prompt_diagnostics
from app.rate_limit import limiter
from app.services.openai_key_utils import openai_api_key_looks_valid
from app.services.integrations import (
    check_anthropic,
    check_google,
    check_openai,
    check_stripe,
    check_supabase,
    check_supabase_auth,
    check_supabase_auth_api_key,
)
from app.services.google_oauth import google_oauth_diagnostics
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
    """Liveness probe — sin dependencias externas (Railway)."""
    from app.services.llama_service import llama_health_diagnostics, llama_model, use_llama

    settings = get_settings()
    payload: dict[str, str] = {
        "status": "ok",
        "service": "castillo-digital-api",
        "env": settings.app_env,
        "build": BUILD_VERSION,
        "timestamp": BUILD_TIMESTAMP,
        "llm_provider": settings.llm_provider,
    }
    if use_llama():
        payload["llama_model"] = llama_model()
        from app.services.llama_service import llama_voice_model

        payload["llama_voice_model"] = llama_voice_model()
        payload["llama_endpoint"] = settings.llama_endpoint.strip()
        diag = llama_health_diagnostics()
        payload["llama_available"] = "true" if diag.get("model_ready") else "false"
        payload["llama_voice_available"] = "true" if diag.get("voice_model_ready") else "false"
        payload["llama_daemon_ok"] = "true" if diag.get("daemon_ok") else "false"
        if not diag.get("model_ready"):
            payload["llama_error"] = str(
                diag.get("error") or "modelo no descargado en Ollama"
            )
            payload["llama_probe_url"] = str(diag.get("url") or "")
    return payload


@router.get("/health/llama")
@limiter.exempt
def health_llama(_request: Request) -> dict:
    """Diagnóstico Llama/Ollama — URL probada, latencia, modelos y error."""
    from app.services.llama_service import llama_health_diagnostics, use_llama

    settings = get_settings()
    if not use_llama():
        return {"enabled": False, "llm_provider": settings.llm_provider}
    return {"enabled": True, **llama_health_diagnostics()}


@router.get("/health/llama/voice-smoke")
@limiter.exempt
def health_llama_voice_smoke(
    _request: Request,
    phrase: str = Query(default="me siento un poco triste hoy"),
) -> dict:
    """Smoke test — Llama 3B con prompt casual mínimo (diagnóstico prod)."""
    import time

    from app.services.llama_service import call_llama_voice_chat, use_llama
    from app.services.voice_casual import (
        LLAMA_CASUAL_MAX_TOKENS,
        LLAMA_CASUAL_TEMPERATURE,
        LLAMA_CASUAL_TIMEOUT_SEC,
        build_casual_llama_system,
    )
    from app.services.voice_response_guard import guard_voice_response
    from app.services.voice_spoken import finalize_voice_delivery_text

    if not use_llama():
        return {"ok": False, "error": "llama disabled"}
    system = build_casual_llama_system(phrase)
    started = time.perf_counter()
    err = ""
    raw = ""
    try:
        raw = call_llama_voice_chat(
            system=system,
            messages=[{"role": "user", "content": phrase}],
            temperature=LLAMA_CASUAL_TEMPERATURE,
            max_tokens=LLAMA_CASUAL_MAX_TOKENS,
            timeout_sec=LLAMA_CASUAL_TIMEOUT_SEC,
        )
    except Exception as exc:  # noqa: BLE001
        err = f"{type(exc).__name__}: {exc}"
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    safe, blocked = guard_voice_response(raw)
    final = finalize_voice_delivery_text(safe) if safe else ""
    return {
        "ok": bool(final) and not err,
        "phrase": phrase[:120],
        "system_chars": len(system),
        "elapsed_ms": elapsed_ms,
        "error": err,
        "raw_preview": (raw or "")[:200],
        "guard_blocked": blocked,
        "final_preview": (final or "")[:200],
        "build": BUILD_VERSION,
    }


@router.get("/health/voice-prompt")
@limiter.exempt
def health_voice_prompt(_request: Request) -> dict:
    """Confirma que el system prompt CED activo está cargado (sin exponer el texto)."""
    settings = get_settings()
    from app.services.gemini_voice_llm import _voice_model

    diag = voice_prompt_diagnostics()
    from app.services.retell_agent_cache import get_last_bootstrap_info

    boot = get_last_bootstrap_info() or {}
    return {
        "status": "ok",
        "build": BUILD_VERSION,
        "env": settings.app_env,
        "voice_model": _voice_model(),
        "conversational_routing": "gemini_2.5_flash_with_ced_prompt",
        "retell_responsiveness": boot.get("responsiveness", 0.78),
        "retell_interruption_sensitivity": boot.get("interruption_sensitivity", 0.50),
        "anti_duplication": "v38_turn_lock",
        **diag,
    }


@router.get("/ready")
@limiter.exempt
def ready(_request: Request) -> dict[str, str]:
    """Alias de health para compatibilidad con probes."""
    settings = get_settings()
    return {
        "status": "ok",
        "service": "castillo-digital-api",
        "env": settings.app_env,
        "build": BUILD_VERSION,
        "timestamp": BUILD_TIMESTAMP,
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
    openai_env_names = sorted(k for k in os.environ if "OPENAI" in k.upper())
    raw_openai = os.environ.get("OPENAI_API_KEY", "")
    return {
        "expected_supabase_project": expected_ref,
        "configured_project_ref": project_ref,
        "project_match": project_ref == expected_ref,
        "has_supabase_url": bool(url),
        "has_service_role_key": bool(settings.supabase_service_role_key.strip()),
        "oauth_token_storage_ready": bool(settings.supabase_service_role_key.strip()),
        "google_oauth": google_oauth_diagnostics(),
        "has_anon_key": bool(settings.supabase_anon_key.strip()),
        "has_jwt_secret": bool(settings.supabase_jwt_secret.strip()),
        "supabase_api_key_valid": supabase_auth.get("ok"),
        "supabase_keys_valid": supabase_auth.get("keys_valid"),
        "supabase_auth_error": supabase_auth.get("error"),
        "super_admin_emails_set": bool(settings.super_admin_emails.strip()),
        "has_anthropic_api_key": bool(settings.anthropic_api_key.strip()),
        "has_openai_api_key": bool(settings.openai_api_key.strip()),
        "openai_api_key_length": len(settings.openai_api_key.strip()),
        "openai_env_var_names": openai_env_names,
        "openai_env_has_raw_key": bool(raw_openai.strip()),
        "openai_key_looks_valid": openai_api_key_looks_valid(settings.openai_api_key),
        "openai_key_prefix": (
            settings.openai_api_key.strip()[:7] + "…"
            if settings.openai_api_key.strip().startswith("sk-")
            else None
        ),
        "hint": (
            "Si has_openai_api_key=false: en Railway servicio CED-WEB agrega "
            "OPENAI_API_KEY=sk-proj-... (sin comillas) y Redeploy. "
            "Revisa openai_env_var_names por typos (ej. OPENAI_KEY)."
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
            "voice_minutes_per_day": CED_ELITE.voice_minutes_per_day,
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
            "openai_voice_cost_per_hour_usd": 12.0,
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
    openai_status = check_openai()
    google_status = check_google()
    anthropic_status = check_anthropic()
    return {
        "phase": 1,
        "supabase_db": supabase_db,
        "supabase_auth": supabase_auth,
        "stripe": stripe_status,
        "openai": openai_status,
        "gemini": google_status,
        "anthropic": anthropic_status,
        "ready": supabase_db.get("ok")
        and stripe_status.get("ok")
        and google_status.get("ok")
        and anthropic_status.get("ok"),
        "chat_ready": google_status.get("ok") or anthropic_status.get("ok"),
    }


@router.get("/v1/recharge/quote")
def recharge_quote(amount_usd: float = Query(..., ge=5, le=500)) -> dict:
    """Cotización en vivo para monto personalizado de recarga."""
    return quote_recharge(amount_usd)
