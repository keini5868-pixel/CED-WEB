"""Perfil del usuario — preferencias de tratamiento y patrocinio FitLine."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.deps.auth import require_user_id
from app.services.opportunities_pilot.fitline_sponsor import (
    resolve_sponsor_url,
    update_user_sponsor_url,
)
from app.services.user_address import resolve_user_address, update_user_address

router = APIRouter(prefix="/v1/profile", tags=["profile"])


class AddressUpdateBody(BaseModel):
    preferred_address: str | None = Field(default=None, max_length=80, alias="preferredAddress")
    gender: Literal["male", "female", "neutral"] | None = None

    model_config = {"populate_by_name": True}


class FitlineSponsorBody(BaseModel):
    url: str | None = Field(default=None, max_length=500)


@router.get("/address")
async def get_address(user_id: str = Depends(require_user_id)) -> dict:
    return resolve_user_address(user_id)


@router.patch("/address")
async def patch_address(
    body: AddressUpdateBody,
    user_id: str = Depends(require_user_id),
) -> dict:
    return update_user_address(
        user_id,
        preferred_address=body.preferred_address,
        gender=body.gender,
    )


@router.get("/fitline-sponsor")
async def get_fitline_sponsor(user_id: str = Depends(require_user_id)) -> dict:
    return {"ok": True, **resolve_sponsor_url(user_id)}


@router.put("/fitline-sponsor")
async def put_fitline_sponsor(
    body: FitlineSponsorBody,
    user_id: str = Depends(require_user_id),
) -> dict:
    result = update_user_sponsor_url(user_id, body.url)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "No se pudo guardar")
    return result
