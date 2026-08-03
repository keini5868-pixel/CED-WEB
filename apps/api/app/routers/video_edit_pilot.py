"""API piloto Video Edit — aislada de voz/chat."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.deps.auth import require_user_id
from app.domain.video_edit_economy import VIDEO_EDIT_TOKEN_PACKS_USD
from app.services.video_edit_pilot.gate import (
    require_video_edit_pilot,
    video_edit_module_pilot_enabled,
)
from app.services.video_edit_pilot import service as video_edit_service

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/video-edit-pilot",
    tags=["video-edit-pilot"],
    dependencies=[Depends(require_video_edit_pilot)],
)

_MAX_UPLOAD_BYTES = 120 * 1024 * 1024  # 120 MB piloto


class QuoteBody(BaseModel):
    duration_sec: float = Field(..., gt=0, le=600)


class RenderBody(BaseModel):
    duration_sec: float = Field(..., gt=0, le=600)
    script: str = Field(default="", max_length=20000)
    source_asset: str = Field(default="upload://pending", max_length=2000)
    auto_transcribe: bool = False


class CheckoutBody(BaseModel):
    amount_usd: float = Field(..., description="10 | 20 | 50")


@router.get("/status")
def video_edit_status() -> dict:
    if not video_edit_module_pilot_enabled():
        raise HTTPException(status_code=404, detail="No disponible.")
    return video_edit_service.pilot_status()


@router.get("/balance")
def video_edit_balance(user_id: str = Depends(require_user_id)) -> dict:
    return video_edit_service.get_balance_payload(user_id)


@router.post("/quote")
def video_edit_quote(
    body: QuoteBody,
    user_id: str = Depends(require_user_id),
) -> dict:
    _ = user_id
    return video_edit_service.quote_job(body.duration_sec)


@router.post("/render")
async def video_edit_render(
    user_id: str = Depends(require_user_id),
    duration_sec: float = Form(...),
    script: str = Form(""),
    auto_transcribe: str = Form("false"),
    video: UploadFile | None = File(None),
) -> dict:
    """Multipart: video (opcional pero requerido para live) + script + duration_sec."""
    auto_flag = str(auto_transcribe or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    video_bytes: bytes | None = None
    filename = "source.mp4"
    content_type = "video/mp4"
    if video is not None:
        raw = await video.read()
        if len(raw) > _MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail="Video demasiado grande (máx. 120 MB en piloto).",
            )
        if raw:
            video_bytes = raw
            filename = (video.filename or "").strip() or filename
            content_type = video.content_type or content_type
        else:
            logger.warning(
                "[VIDEO_EDIT] upload vacío filename=%s content_type=%s",
                video.filename,
                video.content_type,
            )

    result = video_edit_service.plan_and_render(
        user_id,
        duration_sec=duration_sec,
        script=script,
        source_asset=f"upload://{filename}",
        auto_transcribe=auto_flag,
        video_bytes=video_bytes,
        video_filename=filename,
        video_content_type=content_type,
    )
    if not result.get("ok"):
        code = result.get("code") or "render_failed"
        status = 402 if code == "insufficient_tokens" else 400
        if code == "daily_soft_cap":
            status = 429
        if code == "render_failed":
            status = 502
        raise HTTPException(status_code=status, detail=result)
    return result


@router.post("/render-json")
def video_edit_render_json(
    body: RenderBody,
    user_id: str = Depends(require_user_id),
) -> dict:
    """Compat dry-run sin archivo (tests / clientes JSON)."""
    result = video_edit_service.plan_and_render(
        user_id,
        duration_sec=body.duration_sec,
        script=body.script,
        source_asset=body.source_asset,
        auto_transcribe=body.auto_transcribe,
    )
    if not result.get("ok"):
        code = result.get("code") or "render_failed"
        status = 402 if code == "insufficient_tokens" else 400
        if code == "daily_soft_cap":
            status = 429
        raise HTTPException(status_code=status, detail=result)
    return result


@router.post("/checkout")
def video_edit_checkout(
    body: CheckoutBody,
    user_id: str = Depends(require_user_id),
) -> dict:
    amount = int(round(float(body.amount_usd)))
    if amount not in VIDEO_EDIT_TOKEN_PACKS_USD:
        raise HTTPException(
            status_code=400,
            detail=f"Pack no válido. Use uno de: {list(VIDEO_EDIT_TOKEN_PACKS_USD)}",
        )
    from app.services import supabase_db
    from app.services.stripe_billing import create_video_edit_token_checkout

    profile = supabase_db.get_profile(user_id) or {}
    email = str(profile.get("email") or "")
    try:
        return create_video_edit_token_checkout(user_id, email, float(amount))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("[VIDEO_EDIT] checkout failed")
        raise HTTPException(
            status_code=503,
            detail="No se pudo iniciar la compra de tokens de video.",
        ) from exc
