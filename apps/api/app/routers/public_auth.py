"""Auth pública — registro manual email/contraseña (NO Google OAuth)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.deps.auth import require_user_id
from app.rate_limit import limiter
from app.services.public_register import (
    PublicRegisterError,
    register_with_email,
    resend_verification_email,
)

router = APIRouter(prefix="/v1/auth", tags=["auth-public"])


class RegisterBody(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(default="", max_length=120)
    next: str = Field(default="/", max_length=500)
    # Funnel FitLine / CED Cierre: offer=cierre → 20 min voz / 24 h, luego pagar.
    offer: str = Field(default="", max_length=32)


class ResendBody(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    next: str = Field(default="/", max_length=500)


class ApplyOfferBody(BaseModel):
    offer: str = Field(default="cierre", max_length=32)


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
    """Aplica oferta FitLine (cierre) a la cuenta autenticada — p.ej. Google OAuth."""
    from app.domain.plans import CIERRE_TRIAL_OFFER
    from app.services import supabase_db

    offer = (body.offer or "").strip().lower()
    if offer not in (CIERRE_TRIAL_OFFER, "fitline"):
        raise HTTPException(status_code=400, detail="Oferta no válida.")
    result = supabase_db.apply_cierre_fitline_trial(user_id)
    if not result.get("ok"):
        reason = str(result.get("reason") or "error")
        if reason == "already_paid":
            raise HTTPException(
                status_code=409,
                detail="Ya tienes una suscripción de pago activa.",
            )
        raise HTTPException(
            status_code=503, detail="No se pudo activar la prueba FitLine."
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
