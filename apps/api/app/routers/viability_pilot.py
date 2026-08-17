"""HTTP API — Análisis de Producto (producción; kill-switch por env)."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.deps.auth import require_user_id
from app.services.module_usage import log_module_usage_async
from app.services.viability_pilot.gate import (
    require_viability_module_enabled,
    viability_module_enabled,
)
from app.services.viability_pilot.intents import is_viability_module_intent
from app.services.viability_pilot.service import analyze_viability

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/viability-pilot",
    tags=["viability"],
    dependencies=[Depends(require_viability_module_enabled)],
)


class ViabilityAnalyzeRequest(BaseModel):
    description: str | None = Field(default=None, max_length=8000)
    image_base64: str | None = Field(default=None, max_length=12_000_000)
    region: str | None = Field(default=None, max_length=120)
    category_hint: str | None = Field(default=None, max_length=120)
    # Panel dedicado: no exige phrasing; voice/chat sí pueden pre-chequear.
    require_intent_phrasing: bool = False


class ViabilityIntentCheckRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


@router.get("/status")
def viability_status(_user_id: str = Depends(require_user_id)) -> dict:
    from app.config import get_settings

    settings = get_settings()
    return {
        "pilot": False,
        "production": True,
        "enabled": viability_module_enabled(),
        "tavily": bool(settings.tavily_api_key.strip()),
        "google": bool(settings.google_api_key.strip()),
    }


@router.post("/intent-check")
def viability_intent_check(
    body: ViabilityIntentCheckRequest,
    _user_id: str = Depends(require_user_id),
) -> dict:
    return {
        "is_viability_intent": is_viability_module_intent(body.text),
        "production": True,
    }


@router.post("/analyze")
async def viability_analyze(
    body: ViabilityAnalyzeRequest,
    user_id: str = Depends(require_user_id),
) -> dict:
    desc = (body.description or "").strip()
    image = (body.image_base64 or "").strip() or None
    if not desc and not image:
        raise HTTPException(
            status_code=400,
            detail="Envíe description y/o image_base64.",
        )
    if body.require_intent_phrasing and desc and not is_viability_module_intent(desc):
        # Image-only or panel path can skip; this guards mis-routed callers.
        if not image:
            raise HTTPException(
                status_code=400,
                detail=(
                    "El texto no parece un pedido de análisis de viabilidad. "
                    "Use frases como «analiza la viabilidad de…»."
                ),
            )

    try:
        report = await asyncio.to_thread(
            analyze_viability,
            description=desc or None,
            image_b64=image,
            region=(body.region or "").strip() or None,
            category_hint=(body.category_hint or "").strip() or None,
            polish=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("[VIABILITY] analyze failed user=%s", user_id[:8])
        raise HTTPException(
            status_code=502,
            detail="No pude completar el Análisis de Producto. Reintenta.",
        ) from exc

    if not report.get("ok"):
        raise HTTPException(
            status_code=400,
            detail=report.get("message") or "Falta descripción del producto/servicio.",
        )
    await log_module_usage_async(
        user_id=user_id,
        module="viability",
        channel="http",
        metadata={
            "has_image": bool(image),
            "region": (body.region or "").strip() or None,
        },
    )
    return report
