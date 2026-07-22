"""HTTP API piloto — oportunidades de negocio."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException

from app.deps.auth import require_user_id
from app.services.opportunities_pilot.gate import (
    opportunities_pilot_enabled,
    require_opportunities_pilot_header,
)
from app.services.opportunities_pilot.service import (
    get_opportunity_detail,
    list_opportunity_catalog,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/opportunities-pilot",
    tags=["opportunities-pilot"],
    dependencies=[Depends(require_opportunities_pilot_header)],
)


@router.get("/status")
def opportunities_pilot_status(_user_id: str = Depends(require_user_id)) -> dict:
    from app.config import get_settings

    settings = get_settings()
    return {
        "pilot": True,
        "enabled": opportunities_pilot_enabled(),
        "tavily": bool(settings.tavily_api_key.strip()),
        "sponsor_url_configured": bool(
            settings.opportunities_fitline_sponsor_url.strip()
        ),
        "entry": "?opportunitiesModule=pilot",
    }


@router.get("/catalog")
def opportunities_catalog(_user_id: str = Depends(require_user_id)) -> dict:
    return list_opportunity_catalog()


@router.get("/opportunities/{opportunity_id}")
async def opportunity_detail(
    opportunity_id: str,
    user_id: str = Depends(require_user_id),
) -> dict:
    try:
        report = await asyncio.to_thread(
            get_opportunity_detail, opportunity_id.strip()
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "[OPPS-PILOT] detail failed user=%s id=%s",
            user_id[:8],
            opportunity_id[:40],
        )
        raise HTTPException(
            status_code=502,
            detail="No pude cargar la ficha de oportunidad. Reintenta.",
        ) from exc

    if not report.get("ok"):
        raise HTTPException(
            status_code=404,
            detail=report.get("message")
            or "Oportunidad no disponible en el catálogo.",
        )
    return report
