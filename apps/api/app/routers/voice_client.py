"""Puente cliente ↔ servidor para voz Retell (cámara, visión, imágenes)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.deps.auth import require_user_id
from app.services import voice_client_session as vcs
from app.services.publish_media import client_media_url, decode_image_data

router = APIRouter(prefix="/v1/voice", tags=["voice-client"])
logger = logging.getLogger(__name__)

MAX_VOICE_IMAGE_BYTES = 10 * 1024 * 1024
ALLOWED_IMAGE_MIMES = frozenset(
    {
        "image/jpeg",
        "image/jpg",
        "image/png",
        "image/webp",
        "image/gif",
        "image/heic",
        "image/heif",
    },
)


class CameraStatusBody(BaseModel):
    active: bool
    stream_present: bool = Field(default=True, alias="streamPresent")

    model_config = {"populate_by_name": True}


class VisionResultBody(BaseModel):
    request_id: int
    summary: str = Field(min_length=1, max_length=4000)


class AckActionBody(BaseModel):
    action_id: int


class ChatImageBody(BaseModel):
    image_url: str | None = Field(default=None, max_length=4000)
    image_data: str | None = Field(default=None, max_length=15_000_000)
    filename: str | None = Field(default=None, max_length=260)


def _client_url_from_public(public_url: str) -> str:
    file_name = (public_url or "").rsplit("/", 1)[-1].strip()
    return client_media_url(file_name) if file_name else ""


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
    vcs.set_camera_active(
        user_id,
        body.active,
        stream_present=body.stream_present if body.active else False,
    )
    return {
        "ok": "true",
        "active": str(body.active).lower(),
        "stream_present": str(body.stream_present).lower(),
    }


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


@router.post("/chat-image")
async def voice_chat_image(
    body: ChatImageBody,
    user_id: str = Depends(require_user_id),
) -> dict[str, Any]:
    """Registra imagen del HUD para publicar/analizar por voz Retell."""
    filename = (body.filename or "imagen").strip() or "imagen"
    call_id = vcs.ensure_active_voice_call(user_id) or ""

    if body.image_data:
        try:
            raw, mime = decode_image_data(body.image_data)
        except ValueError as exc:
            logger.warning("[VOICE_UPLOAD] user=%s decode_error=%s", user_id[:8], exc)
            raise HTTPException(status_code=400, detail="Formato de imagen no soportado.") from exc
        if mime.lower() not in ALLOWED_IMAGE_MIMES:
            raise HTTPException(
                status_code=400,
                detail="Formato no soportado. Usa JPG, PNG, WebP o GIF.",
            )
        if len(raw) > MAX_VOICE_IMAGE_BYTES:
            raise HTTPException(
                status_code=400,
                detail="Imagen muy grande. Máximo 10 MB.",
            )
        public_url = vcs.set_last_publishable_image_from_bytes(
            user_id,
            raw,
            mime,
            awaiting_caption=False,
            filename=filename,
        )
        client_url = _client_url_from_public(public_url)
        logger.info(
            "[VOICE_UPLOAD] user=%s file=%s size=%s status=ok call=%s",
            user_id[:8],
            filename[:48],
            len(raw),
            (call_id or "?")[:12],
        )
        return {
            "ok": True,
            "image_url": client_url or public_url,
            "public_url": public_url,
            "size_bytes": len(raw),
            "filename": filename,
        }

    url = (body.image_url or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="Imagen vacía.")
    vcs.set_last_publishable_image(
        user_id,
        image_url=url,
        awaiting_caption=False,
        filename=filename,
    )
    from app.services.publish_image_context import register_voice_session_image

    register_voice_session_image(
        user_id,
        url,
        filename=filename,
        session_id=call_id or None,
    )
    logger.info(
        "[VOICE_UPLOAD] user=%s file=%s status=ok_url call=%s",
        user_id[:8],
        filename[:48],
        (call_id or "?")[:12],
    )
    return {
        "ok": True,
        "image_url": url if url.startswith("/") else _client_url_from_public(url) or url,
        "public_url": url,
        "filename": filename,
    }


@router.delete("/chat-image")
async def voice_clear_chat_image(
    user_id: str = Depends(require_user_id),
) -> dict[str, str]:
    vcs.clear_last_publishable_image(user_id)
    logger.info("[VOICE_UPLOAD] user=%s status=cleared", user_id[:8])
    return {"ok": "true"}


@router.post("/session-end")
async def voice_session_end(
    user_id: str = Depends(require_user_id),
) -> dict[str, str]:
    """Fin de sesión voz en cliente — limpia imagen pendiente."""
    vcs.end_voice_publish_session(user_id)
    return {"ok": "true"}
