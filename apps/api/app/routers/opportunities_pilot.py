"""HTTP API — oportunidades de negocio (producción; kill-switch por env)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.deps.auth import require_user_id
from app.services.module_usage import log_module_usage_async
from app.services.opportunities_pilot.fitline_action_plans import (
    archive_active_plan,
    get_active_plan,
    list_plans,
    upsert_active_plan,
)
from app.services.opportunities_pilot.fitline_sponsor import (
    resolve_sponsor_url,
    update_user_sponsor_url,
)
from app.services.opportunities_pilot.gate import (
    opportunities_module_enabled,
    require_opportunities_module_enabled,
)
from app.services.opportunities_pilot.service import (
    get_opportunity_detail,
    list_opportunity_catalog,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/opportunities-pilot",
    tags=["opportunities"],
    dependencies=[Depends(require_opportunities_module_enabled)],
)


class SponsorUrlBody(BaseModel):
    url: str | None = Field(default=None, max_length=500)


class ActionPlanBody(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    content: dict[str, Any] | None = None
    merge_content: bool = Field(default=True, alias="mergeContent")

    model_config = {"populate_by_name": True}


@router.get("/status")
def opportunities_status(user_id: str = Depends(require_user_id)) -> dict:
    from app.config import get_settings

    settings = get_settings()
    sponsor = resolve_sponsor_url(user_id)
    plan = get_active_plan(user_id)
    return {
        "pilot": False,
        "production": True,
        "enabled": opportunities_module_enabled(),
        "tavily": bool(settings.tavily_api_key.strip()),
        "live_search": bool(settings.opportunities_live_search),
        "curated_only": not bool(settings.opportunities_live_search),
        "sponsor_url_configured": bool(sponsor.get("configured")),
        "sponsor": sponsor,
        "has_action_plan": bool(plan),
    }


@router.get("/catalog")
def opportunities_catalog(_user_id: str = Depends(require_user_id)) -> dict:
    return list_opportunity_catalog()


@router.get("/sponsor")
def get_sponsor(user_id: str = Depends(require_user_id)) -> dict:
    return {"ok": True, **resolve_sponsor_url(user_id)}


@router.put("/sponsor")
def put_sponsor(
    body: SponsorUrlBody,
    user_id: str = Depends(require_user_id),
) -> dict:
    result = update_user_sponsor_url(user_id, body.url)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "No se pudo guardar")
    return result


@router.get("/action-plan")
def get_action_plan(user_id: str = Depends(require_user_id)) -> dict:
    plan = get_active_plan(user_id)
    return {"ok": True, "plan": plan, "plans": list_plans(user_id, limit=5)}


@router.put("/action-plan")
def put_action_plan(
    body: ActionPlanBody,
    user_id: str = Depends(require_user_id),
) -> dict:
    result = upsert_active_plan(
        user_id,
        title=body.title,
        content=body.content,
        merge_content=body.merge_content,
    )
    if not result.get("ok"):
        raise HTTPException(
            status_code=502,
            detail=result.get("detail") or "No se pudo guardar el plan. ¿Migración 027 aplicada?",
        )
    return result


@router.delete("/action-plan")
def delete_action_plan(user_id: str = Depends(require_user_id)) -> dict:
    return archive_active_plan(user_id)


@router.get("/opportunities/{opportunity_id}")
async def opportunity_detail(
    opportunity_id: str,
    user_id: str = Depends(require_user_id),
) -> dict:
    try:
        report = await asyncio.to_thread(
            get_opportunity_detail,
            opportunity_id.strip(),
            user_id=user_id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "[OPPS] detail failed user=%s id=%s",
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
    await log_module_usage_async(
        user_id=user_id,
        module="opportunities",
        channel="http",
        metadata={"opportunity_id": opportunity_id.strip()[:80]},
    )
    return report
