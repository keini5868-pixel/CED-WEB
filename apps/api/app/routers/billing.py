"""Stripe — suscripciones + recargas."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.deps.auth import require_super_admin, require_user_id
from app.config import get_settings
from app.domain.plans import (
    RECHARGE_MAX_USD,
    RECHARGE_MIN_USD,
    STRIPE_CHECKOUT_PLANS,
    public_plans_catalog,
    quote_recharge,
)
from app.services import supabase_db
from app.services.integrations import check_stripe, check_supabase
from app.services.stripe_billing import (
    confirm_checkout_session,
    create_portal_session,
    create_recharge_checkout,
    create_subscription_checkout,
    ensure_stripe_plan_price,
    founding_slots_available,
    handle_stripe_event,
    recharge_catalog,
    verify_webhook,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/billing", tags=["billing"])


class SubscriptionCheckoutBody(BaseModel):
    plan_id: str = Field(..., description="cierre | starter | pro | elite | founding")


class RechargeCheckoutBody(BaseModel):
    amount_usd: float = Field(..., ge=RECHARGE_MIN_USD, le=RECHARGE_MAX_USD)


class FreeBasicBody(BaseModel):
    confirm: bool = True


class ConfirmCheckoutBody(BaseModel):
    session_id: str = Field(..., min_length=8, max_length=200)


@router.get("/plans")
def list_plans() -> dict:
    used, cap = founding_slots_available()
    return {
        "plans": public_plans_catalog(),
        "founding_slots_used": used,
        "founding_slots_max": cap,
        "recharge_amounts": recharge_catalog(),
    }


@router.get("/readiness")
def billing_readiness(
    _admin_id: str = Depends(require_super_admin),
) -> dict:
    """Estado Stripe + precios — solo super admin."""
    settings = get_settings()
    stripe_status = check_stripe()
    supa = check_supabase()
    price_vars = {
        "cierre": bool(settings.stripe_price_cierre.strip()),
        "starter": bool(settings.stripe_price_starter.strip()),
        "pro": bool(settings.stripe_price_pro.strip()),
        "elite": bool(settings.stripe_price_elite.strip()),
        "founding": bool(settings.stripe_price_founding.strip()),
        "recharge_10": bool(settings.stripe_price_recharge_10.strip()),
        "webhook_secret": bool(settings.stripe_webhook_secret.strip()),
        "publishable_hint": "NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY en web",
    }
    prices_ok = all(
        [
            settings.stripe_price_starter.strip(),
            settings.stripe_price_pro.strip(),
            settings.stripe_price_elite.strip(),
            settings.stripe_price_founding.strip(),
        ]
    )
    livemode = bool(stripe_status.get("livemode"))
    key_mode = stripe_status.get("key_mode", "unknown")
    return {
        "ok": bool(stripe_status.get("ok")) and prices_ok and supa.get("ok"),
        "livemode": livemode,
        "charges_real_money": livemode,
        "stripe": stripe_status,
        "supabase": {"ok": supa.get("ok"), "error": supa.get("error")},
        "prices_configured": price_vars,
        "webhook_urls": [
            f"{settings.api_public_url.rstrip('/')}/v1/billing/webhook",
            f"{settings.api_public_url.rstrip('/')}/v1/billing/webhooks/stripe",
        ],
        "live_checklist": None
        if livemode
        else {
            "reason": f"STRIPE_SECRET_KEY es modo {key_mode} (sk_test_ = prueba, sk_live_ = cobros reales)",
            "steps": [
                "Stripe Dashboard → activar Live (no Test)",
                "Copiar Secret key sk_live_... → Railway API STRIPE_SECRET_KEY",
                "Copiar Publishable pk_live_... → Railway Web NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY",
                "Crear productos/precios en Live y copiar price_... LIVE a STRIPE_PRICE_*",
                "Webhooks en Live → endpoint /v1/billing/webhook → STRIPE_WEBHOOK_SECRET (whsec_ live)",
                "Redeploy API + Web y verificar livemode: true en /v1/billing/readiness",
            ],
        },
    }


@router.post("/ensure-cierre-product")
def ensure_cierre_product(
    _admin_id: str = Depends(require_super_admin),
) -> dict:
    """Crea o reutiliza Product+Price Stripe de CED Cierre ($20/mes)."""
    try:
        price_id = ensure_stripe_plan_price("cierre")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("[BILLING] ensure cierre product failed")
        raise HTTPException(
            status_code=503, detail="No se pudo crear el producto en Stripe."
        ) from exc
    return {
        "ok": True,
        "plan_id": "cierre",
        "price_id": price_id,
        "hint": "Copia price_id a Railway STRIPE_PRICE_CIERRE (opcional si ya se auto-crea).",
    }


@router.post("/checkout/subscription")
def checkout_subscription(
    body: SubscriptionCheckoutBody,
    user_id: str = Depends(require_user_id),
) -> dict:
    plan_id = body.plan_id.strip().lower()
    if plan_id not in STRIPE_CHECKOUT_PLANS:
        raise HTTPException(status_code=400, detail="Plan no válido.")
    profile = supabase_db.get_profile(user_id) or {}
    email = str(profile.get("email") or "")
    try:
        return create_subscription_checkout(user_id, email, plan_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("[BILLING] subscription checkout failed")
        raise HTTPException(status_code=503, detail="No se pudo iniciar el pago.") from exc


@router.post("/checkout/recharge")
def checkout_recharge(
    body: RechargeCheckoutBody,
    user_id: str = Depends(require_user_id),
) -> dict:
    profile = supabase_db.get_profile(user_id) or {}
    email = str(profile.get("email") or "")
    try:
        result = create_recharge_checkout(user_id, email, body.amount_usd)
        return {**result, "quote": quote_recharge(body.amount_usd)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("[BILLING] recharge checkout failed")
        raise HTTPException(status_code=503, detail="No se pudo iniciar la recarga.") from exc


@router.post("/confirm-checkout")
def confirm_checkout(
    body: ConfirmCheckoutBody,
    user_id: str = Depends(require_user_id),
) -> dict:
    """Tras volver de Stripe: acredita plan/recarga si el webhook aún no lo hizo."""
    try:
        return confirm_checkout_session(body.session_id.strip(), user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("[BILLING] confirm-checkout failed")
        raise HTTPException(
            status_code=503, detail="No se pudo confirmar el pago."
        ) from exc


@router.post("/portal")
def billing_portal(user_id: str = Depends(require_user_id)) -> dict:
    try:
        return create_portal_session(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("[BILLING] portal failed")
        raise HTTPException(status_code=503, detail="Portal no disponible.") from exc


@router.post("/trial/continue-free")
def continue_free_basic(
    body: FreeBasicBody,
    user_id: str = Depends(require_user_id),
) -> dict:
    """Al expirar trial, el usuario elige plan básico gratis."""
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Confirmación requerida.")
    supabase_db.downgrade_to_free_basic(user_id)
    return {"ok": True, "plan_id": "free_basic"}


@router.post("/admin/reconcile-stale-access")
def admin_reconcile_stale_access(
    dry_run: bool = False,
    _admin_id: str = Depends(require_super_admin),
) -> dict:
    """Downgrade trials vencidos y lista past_due (acceso gated en runtime)."""
    return supabase_db.reconcile_stale_access(dry_run=dry_run)


async def _stripe_webhook_handler(request: Request) -> dict:
    payload = await request.body()
    sig = request.headers.get("stripe-signature")
    try:
        event = verify_webhook(payload, sig)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("[BILLING] webhook signature invalid")
        raise HTTPException(status_code=400, detail="Firma webhook inválida.") from exc

    try:
        handle_stripe_event(event)
    except Exception:  # noqa: BLE001
        logger.exception("[BILLING] webhook handler error event=%s", event.get("id"))
        raise HTTPException(status_code=500, detail="Error procesando webhook.")

    return {"received": True}


@router.post("/webhook")
async def stripe_webhook(request: Request) -> dict:
    """Endpoint principal — URL en Stripe Dashboard."""
    return await _stripe_webhook_handler(request)


@router.post("/webhooks/stripe")
async def stripe_webhook_legacy(request: Request) -> dict:
    """Alias legacy."""
    return await _stripe_webhook_handler(request)
