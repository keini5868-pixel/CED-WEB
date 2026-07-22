"""HTTP API piloto — tendencias de industria."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.deps.auth import require_user_id
from app.services.trends_pilot.gate import (
    require_trends_pilot_header,
    trends_pilot_enabled,
)
from app.services.trends_pilot.intents import is_trends_module_intent
from app.services.trends_pilot.service import analyze_trends

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/trends-pilot",
    tags=["trends-pilot"],
    dependencies=[Depends(require_trends_pilot_header)],
)


class TrendsAnalyzeRequest(BaseModel):
    description: str = Field(min_length=1, max_length=8000)
    region: str | None = Field(default=None, max_length=120)


class TrendsIntentCheckRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


@router.get("/status")
def trends_pilot_status(_user_id: str = Depends(require_user_id)) -> dict:
    from app.config import get_settings

    settings = get_settings()
    return {
        "pilot": True,
        "enabled": trends_pilot_enabled(),
        "tavily": bool(settings.tavily_api_key.strip()),
        "google": bool(settings.google_api_key.strip()),
        "entry": "?trendsModule=pilot",
    }


@router.post("/intent-check")
def trends_intent_check(
    body: TrendsIntentCheckRequest,
    _user_id: str = Depends(require_user_id),
) -> dict:
    return {
        "is_trends_intent": is_trends_module_intent(body.text),
        "pilot": True,
    }


@router.post("/analyze")
async def trends_analyze(
    body: TrendsAnalyzeRequest,
    user_id: str = Depends(require_user_id),
) -> dict:
    try:
        report = await asyncio.to_thread(
            analyze_trends,
            description=body.description.strip(),
            region=(body.region or "").strip() or None,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("[TRENDS-PILOT] analyze failed user=%s", user_id[:8])
        raise HTTPException(
            status_code=502,
            detail="No pude completar el análisis de tendencias. Reintenta.",
        ) from exc

    if not report.get("ok"):
        raise HTTPException(
            status_code=400,
            detail=report.get("message") or "Falta descripción del rubro.",
        )
    return report
