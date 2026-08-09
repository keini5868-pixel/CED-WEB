"""Auth pública — registro manual email/contraseña (NO Google OAuth)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.rate_limit import limiter
from app.services.public_register import PublicRegisterError, register_with_email, resend_verification_email

router = APIRouter(prefix="/v1/auth", tags=["auth-public"])


class RegisterBody(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(default="", max_length=120)
    next: str = Field(default="/", max_length=500)


class ResendBody(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    next: str = Field(default="/", max_length=500)


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
        )
    except PublicRegisterError as exc:
        status = 409 if exc.code == "email_exists" else 400
        if exc.code == "resend_not_configured":
            status = 503
        raise HTTPException(status_code=status, detail=exc.message) from exc


@router.post("/resend-verification")
@limiter.limit("5/minute")
def public_resend_verification(request: Request, body: ResendBody) -> dict:
    try:
        return resend_verification_email(email=body.email, next_path=body.next)
    except PublicRegisterError as exc:
        status = 503 if exc.code == "resend_not_configured" else 400
        raise HTTPException(status_code=status, detail=exc.message) from exc
