"""Referidos — Referral ID y dashboard Mi equipo / Mis Invitados."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.deps.auth import require_user_id
from app.services.referrals import (
    add_structure_partner,
    claim_referral,
    complete_pm_profile,
    list_my_team,
)

router = APIRouter(prefix="/v1/referrals", tags=["referrals"])
dashboard_router = APIRouter(prefix="/v1/dashboard", tags=["referrals"])


class ClaimBody(BaseModel):
    code: str = Field(default="", max_length=32)
    ref: str = Field(default="", max_length=32)


class PartnerBody(BaseModel):
    full_name: str = Field(default="", max_length=160)
    email: str = Field(default="", max_length=320)
    pm_partner_id: str = Field(default="", max_length=40)
    ced_id: str = Field(default="", max_length=40)


class ProfileBody(BaseModel):
    full_name: str = Field(default="", max_length=160)
    pm_partner_id: str = Field(default="", max_length=40)
    sponsor_ced_id: str = Field(default="", max_length=32)


def _team_payload(user_id: str) -> dict:
    return list_my_team(user_id)


def _raise_referral_error(result: dict) -> None:
    reason = str(result.get("reason") or "error")
    if reason == "unknown_code":
        raise HTTPException(status_code=404, detail="Código de invitación CED no válido.")
    if reason == "self":
        raise HTTPException(
            status_code=400, detail="No puedes usar tu propio código de invitación."
        )
    if reason == "invalid_name":
        raise HTTPException(
            status_code=400, detail="Escribe el nombre completo (mínimo 3 letras)."
        )
    if reason == "invalid_email":
        raise HTTPException(status_code=400, detail="Correo no válido.")
    if reason == "invalid_ced_id":
        raise HTTPException(status_code=400, detail="Código de invitación CED no válido.")
    if reason == "invalid_pm_partner_id":
        raise HTTPException(
            status_code=400,
            detail="Escribe el ID de socio de PM International (Partner Area).",
        )
    if reason == "ced_id_mismatch":
        raise HTTPException(
            status_code=400,
            detail="Ese ID no corresponde a un socio de PM International.",
        )
    raise HTTPException(status_code=400, detail="No se pudo guardar el socio.")


@router.get("/me", name="referrals_me")
@dashboard_router.get("/mi-equipo", name="dashboard_mi_equipo")
def my_team(user_id: str = Depends(require_user_id)) -> dict:
    """Lista invitados del socio autenticado + su Referral ID.

    Criterio: uso real para vender PM/FitLine (voz, chat de venta, Finanzas, OPPS),
    no actividad genérica del sistema.
    """
    return _team_payload(user_id)


@router.post("/claim")
def claim(body: ClaimBody, user_id: str = Depends(require_user_id)) -> dict:
    result = claim_referral(user_id, body.code or body.ref)
    if not result.get("ok"):
        _raise_referral_error(result)
    return result


@router.post("/profile")
def save_pm_profile(body: ProfileBody, user_id: str = Depends(require_user_id)) -> dict:
    result = complete_pm_profile(
        user_id,
        full_name=body.full_name,
        pm_partner_id=body.pm_partner_id,
        sponsor_ced_id=body.sponsor_ced_id,
    )
    if not result.get("ok"):
        _raise_referral_error(result)
    return result


@router.post("/partners")
def create_partner(body: PartnerBody, user_id: str = Depends(require_user_id)) -> dict:
    result = add_structure_partner(
        user_id,
        full_name=body.full_name,
        email=body.email,
        ced_id=body.ced_id,
        pm_partner_id=body.pm_partner_id,
    )
    if not result.get("ok"):
        _raise_referral_error(result)
    return result
