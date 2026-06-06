"""Visión — análisis de imagen y búsqueda web de lo visible."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.deps.auth import require_user_id
from app.services.vision_search import analyze_image, vision_search_web

router = APIRouter(prefix="/v1/vision", tags=["vision"])


class VisionBody(BaseModel):
    image: str = Field(description="JPEG base64 o data URL")
    question: str = Field(default="", max_length=500)


@router.post("/analyze")
async def vision_analyze(
    body: VisionBody,
    _user_id: str = Depends(require_user_id),
) -> dict:
    return await asyncio.to_thread(analyze_image, body.image, question=body.question)


@router.post("/search-web")
async def vision_web_search(
    body: VisionBody,
    _user_id: str = Depends(require_user_id),
) -> dict:
    return await asyncio.to_thread(
        vision_search_web, body.image, question=body.question
    )
