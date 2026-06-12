"""Perfil del usuario — preferencias de tratamiento."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.deps.auth import require_user_id
from app.services.user_address import resolve_user_address, update_user_address

router = APIRouter(prefix="/v1/profile", tags=["profile"])


class AddressUpdateBody(BaseModel):
    preferred_address: str | None = Field(default=None, max_length=80, alias="preferredAddress")
    gender: Literal["male", "female", "neutral"] | None = None

    model_config = {"populate_by_name": True}


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
