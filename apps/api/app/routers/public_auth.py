"""Auth pública — registro manual email/contraseña (NO Google OAuth)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.deps.auth import require_user_id
from app.rate_limit import limiter
from app.services.public_register import (
    PublicRegisterError,
    register_with_email,
    resend_verification_email,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/auth", tags=["auth-public"])


class RegisterBody(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=3, max_length=120)
    next: str = Field(default="/", max_length=500)
    # Funnel FitLine / CED PM: offer=cierre → plan PM + 15 min voz desde registro.
    # El resto de altas también reciben 15 min totales (sin plan PM).
    offer: str = Field(default="", max_length=32)
    ref: str = Field(default="", max_length=32)
    pm_partner_id: str = Field(default="", max_length=40)


class ResendBody(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    next: str = Field(default="/", max_length=500)


class ApplyOfferBody(BaseModel):
    offer: str = Field(default="cierre", max_length=32)
    ref: str = Field(default="", max_length=32)


@router.post("/register")
@limiter.limit("8/minute")
def public_register(request: Request, body: RegisterBody) -> dict:
    """Registro manual → correo de verificación vía Resend.

    No modifica el flujo Google OAuth del frontend.
    """
    try:
        return register_with_email(
            email=body.email,
            password=body.password,
            full_name=body.full_name,
            next_path=body.next,
            offer=body.offer,
            ref=body.ref,
            pm_partner_id=body.pm_partner_id,
        )
    except PublicRegisterError as exc:
        status = 409 if exc.code == "email_exists" else 400
        if exc.code == "resend_not_configured":
            status = 503
        raise HTTPException(status_code=status, detail=exc.message) from exc


@router.post("/apply-offer")
@limiter.limit("10/minute")
def apply_offer(
    request: Request,
    body: ApplyOfferBody,
    user_id: str = Depends(require_user_id),
) -> dict:
    """Aplica trial de voz 15 min desde el registro (Google OAuth). offer=cierre → plan PM."""
    from app.domain.plans import CIERRE_TRIAL_OFFER
    from app.services import supabase_db
    from app.services.referrals import claim_referral

    if (body.ref or "").strip():
        try:
            claim_referral(user_id, body.ref)
        except Exception:
            logger.exception("apply-offer: claim_referral failed")

    offer = (body.offer or "").strip().lower()
    if offer in (CIERRE_TRIAL_OFFER, "fitline"):
        result = supabase_db.apply_cierre_fitline_trial(user_id)
    else:
        result = supabase_db.apply_voice_pool_trial(user_id)
    if not result.get("ok"):
        reason = str(result.get("reason") or "error")
        if reason in ("legacy_trial", "not_eligible"):
            return {"ok": True, "skipped": reason}
        if reason == "already_paid":
            if offer in (CIERRE_TRIAL_OFFER, "fitline"):
                raise HTTPException(
                    status_code=409,
                    detail="Ya tienes una suscripción de pago activa.",
                )
            return {"ok": True, "skipped": reason}
        raise HTTPException(
            status_code=503,
            detail="No se pudo activar la prueba de voz.",
        )
    return result


@router.post("/resend-verification")
@limiter.limit("5/minute")
def public_resend_verification(request: Request, body: ResendBody) -> dict:
    try:
        return resend_verification_email(email=body.email, next_path=body.next)
    except PublicRegisterError as exc:
        status = 503 if exc.code == "resend_not_configured" else 400
        raise HTTPException(status_code=status, detail=exc.message) from exc
