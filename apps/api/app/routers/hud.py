"""HUD — carrusel izquierdo y health detallado."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.deps.auth import require_user_id
from app.services.hud_carousel import build_carousel_snapshot
from app.services.hud_health import build_detailed_health

router = APIRouter(prefix="/v1", tags=["hud"])


@router.get("/hud/carousel")
async def hud_carousel(user_id: str = Depends(require_user_id)) -> dict:
    """Snapshot de las 7 tarjetas del carrusel CASTILLO."""
    return build_carousel_snapshot(user_id)


@router.get("/health/detailed")
async def health_detailed(_user_id: str = Depends(require_user_id)) -> dict:
    """Health agregado SaaS — tarjeta SYSTEM."""
    return build_detailed_health()
