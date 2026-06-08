"""Stripe — suscripciones + recargas."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.deps.auth import require_user_id
from app.domain.plans import (
    RECHARGE_MAX_USD,
    RECHARGE_MIN_USD,
    STRIPE_CHECKOUT_PLANS,
    public_plans_catalog,
    quote_recharge,
)
from app.services import supabase_db
from app.services.stripe_billing import (
    create_portal_session,
    create_recharge_checkout,
    create_subscription_checkout,
    founding_slots_available,
    handle_stripe_event,
    recharge_catalog,
    verify_webhook,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/billing", tags=["billing"])


class SubscriptionCheckoutBody(BaseModel):
    plan_id: str = Field(..., description="starter | pro | elite | founding")


class RechargeCheckoutBody(BaseModel):
    amount_usd: float = Field(..., ge=RECHARGE_MIN_USD, le=RECHARGE_MAX_USD)


class FreeBasicBody(BaseModel):
    confirm: bool = True


@router.get("/plans")
def list_plans() -> dict:
    used, cap = founding_slots_available()
    return {
        "plans": public_plans_catalog(),
        "founding_slots_used": used,
        "founding_slots_max": cap,
        "recharge_amounts": recharge_catalog(),
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
