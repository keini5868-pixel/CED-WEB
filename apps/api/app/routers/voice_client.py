"""Puente cliente ↔ servidor para voz Retell (cámara, visión)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.deps.auth import require_user_id
from app.services import voice_client_session as vcs

router = APIRouter(prefix="/v1/voice", tags=["voice-client"])


class CameraStatusBody(BaseModel):
    active: bool


class VisionResultBody(BaseModel):
    request_id: int
    summary: str = Field(min_length=1, max_length=4000)


class AckActionBody(BaseModel):
    action_id: int


@router.get("/client-state")
async def voice_client_state(
    user_id: str = Depends(require_user_id),
    consume: bool = False,
) -> dict[str, Any]:
    return {"ok": True, **vcs.get_state(user_id, consume_action=consume)}


@router.post("/camera-status")
async def voice_camera_status(
    body: CameraStatusBody,
    user_id: str = Depends(require_user_id),
) -> dict[str, str]:
    vcs.set_camera_active(user_id, body.active)
    return {"ok": "true", "active": str(body.active).lower()}


@router.post("/vision-result")
async def voice_vision_result(
    body: VisionResultBody,
    user_id: str = Depends(require_user_id),
) -> dict[str, str]:
    vcs.set_vision_result(user_id, body.request_id, body.summary)
    return {"ok": "true"}


@router.post("/ack-action")
async def voice_ack_action(
    body: AckActionBody,
    user_id: str = Depends(require_user_id),
) -> dict[str, str]:
    vcs.consume_client_action(user_id, body.action_id)
    return {"ok": "true"}
