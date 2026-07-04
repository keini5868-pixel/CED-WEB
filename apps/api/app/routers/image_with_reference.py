"""Generación de imágenes con referencia visual."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.deps.auth import require_user_id
from app.services.image_reference_generator import generate_image_with_reference

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/images", tags=["images"])


@router.post("/generate-with-reference")
async def generate_with_reference(
    prompt: str = Form(...),
    reference_image: UploadFile = File(...),
    style_mode: str = Form("inspired"),
    quality: str = Form("standard"),
    user_id: str = Depends(require_user_id),
) -> dict:
    """
    Genera imagen basada en una imagen de referencia.

    Modos:
    - inspired: usa la imagen como inspiración estilística
    - variation: genera variaciones similares
    - edit: edita partes específicas de la imagen
    """
    if style_mode not in ("inspired", "variation", "edit"):
        raise HTTPException(status_code=400, detail="style_mode debe ser inspired, variation o edit.")

    if quality not in ("standard", "hd", "auto"):
        quality = "standard"

    try:
        reference_data = await reference_image.read()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Reference image read error")
        raise HTTPException(status_code=400, detail="No se pudo leer la imagen.") from exc

    result = await asyncio.to_thread(
        generate_image_with_reference,
        user_id=user_id,
        prompt=prompt,
        reference_image=reference_data,
        content_type=reference_image.content_type,
        style_mode=style_mode,
        quality=quality,
    )

    if not result.get("ok"):
        code = result.get("code", "")
        status = 429 if code == "quota_exhausted" else 403 if code == "plan_limit" else 400
        if code in ("openai_error", "storage_error", "config_error", "internal_error", "gemini_error"):
            status = 502 if code != "config_error" else 503
        raise HTTPException(status_code=status, detail=result.get("error", "Error generando imagen."))

    return result
