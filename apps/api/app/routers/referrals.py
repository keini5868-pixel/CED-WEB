"""Referidos — Referral ID y dashboard Mi equipo / Mis Invitados."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.deps.auth import require_user_id
from app.services.referrals import claim_referral, list_my_team

router = APIRouter(prefix="/v1/referrals", tags=["referrals"])
dashboard_router = APIRouter(prefix="/v1/dashboard", tags=["referrals"])


class ClaimBody(BaseModel):
    code: str = Field(default="", max_length=32)
    ref: str = Field(default="", max_length=32)


def _team_payload(user_id: str) -> dict:
    return list_my_team(user_id)


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
        reason = str(result.get("reason") or "error")
        if reason == "unknown_code":
            raise HTTPException(status_code=404, detail="Referral ID no válido.")
        if reason == "self":
            raise HTTPException(
                status_code=400, detail="No puedes usar tu propio Referral ID."
            )
        raise HTTPException(status_code=400, detail="No se pudo vincular el referido.")
    return result
