"""Stripe — suscripción única + recargas flexibles (stubs Fase 0)."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.domain.plans import quote_recharge

router = APIRouter(prefix="/v1/billing", tags=["billing"])


class RechargeCheckoutRequest(BaseModel):
    amount_usd: float = Field(..., ge=5, le=500, description="Monto USD $5–$500")


@router.post("/checkout/subscription")
def checkout_subscription_stub(plan: str = "elite_founding") -> dict[str, str]:
    """Fase 7: Stripe Checkout — elite_founding o elite_regular."""
    return {"status": "not_implemented", "phase": 7, "plan": plan}


@router.post("/checkout/recharge")
def checkout_recharge_stub(body: RechargeCheckoutRequest) -> dict:
    """Fase 7: Payment Intent por monto flexible; webhook acredita saldo."""
    quote = quote_recharge(body.amount_usd)
    return {
        "status": "not_implemented",
        "phase": 7,
        "quote": quote,
    }


@router.post("/webhooks/stripe")
def stripe_webhook_stub() -> dict[str, str]:
    """Fase 7: verificar firma; subscription + recharge balance."""
    return {"status": "not_implemented", "phase": 7}
