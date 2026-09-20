"""HTTP CED Shield — aislado de voz/chat.

GET /status es público (kill-switch visible). Wallet/seal 404 si CED_SHIELD_ENABLED=false.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.deps.auth import require_user_id
from app.services.ced_shield.gate import require_ced_shield
from app.services.ced_shield import service as shield_service

router = APIRouter(
    prefix="/v1/shield",
    tags=["ced-shield"],
)


class WalletBody(BaseModel):
    address: str = Field(..., min_length=8, max_length=128)


class SealBody(BaseModel):
    kind: str = Field(..., min_length=3, max_length=16)
    file_id: str = Field(default="", max_length=80)
    content_sha256: str = Field(default="", max_length=64)
    tx_ref: str = Field(default="", max_length=128)


@router.get("/status")
def shield_status() -> dict:
    return shield_service.status_payload()


@router.post("/wallet", dependencies=[Depends(require_ced_shield)])
def shield_connect_wallet(
    body: WalletBody,
    user_id: str = Depends(require_user_id),
) -> dict:
    result = shield_service.connect_wallet(user_id, body.address)
    if not result.get("ok"):
        raise HTTPException(status_code=422, detail=result.get("error") or "Wallet inválida.")
    return result


@router.post("/seal", dependencies=[Depends(require_ced_shield)])
def shield_seal(
    body: SealBody,
    user_id: str = Depends(require_user_id),
) -> dict:
    result = shield_service.seal_artifact(
        user_id,
        kind=body.kind,
        file_id=body.file_id,
        content_sha256=body.content_sha256,
        tx_ref=body.tx_ref,
    )
    if not result.get("ok"):
        code = str(result.get("code") or "")
        status = 409 if code == "wallet_required" else 422
        if code == "disabled":
            status = 404
        raise HTTPException(status_code=status, detail=result.get("error") or "No pude sellar.")
    return result


@router.get("/seals", dependencies=[Depends(require_ced_shield)])
def shield_list_seals(user_id: str = Depends(require_user_id)) -> dict:
    return shield_service.wallet_and_seals(user_id)
