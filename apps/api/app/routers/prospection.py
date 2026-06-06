"""Modo prospección — API REST."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.deps.auth import require_user_id
from app.services.prospection import (
    get_prospection_report,
    get_prospection_status,
    scan_instagram_leads,
    set_prospection_enabled,
)

router = APIRouter(prefix="/v1/prospection", tags=["prospection"])


@router.get("/status")
async def prospection_status(user_id: str = Depends(require_user_id)) -> dict:
    return get_prospection_status(user_id)


@router.post("/enable")
async def prospection_enable(user_id: str = Depends(require_user_id)) -> dict:
    return set_prospection_enabled(user_id, True)


@router.post("/disable")
async def prospection_disable(user_id: str = Depends(require_user_id)) -> dict:
    return set_prospection_enabled(user_id, False)


@router.get("/report")
async def prospection_report(user_id: str = Depends(require_user_id)) -> dict:
    return get_prospection_report(user_id)


@router.post("/scan")
async def prospection_scan(user_id: str = Depends(require_user_id)) -> dict:
    """Escaneo manual de comentarios IG."""
    import asyncio

    return await asyncio.to_thread(scan_instagram_leads, user_id)
