"""HUD — carrusel izquierdo y health detallado."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.deps.auth import require_user_id
from app.services.hud_carousel import build_carousel_snapshot
from app.services.hud_health import build_detailed_health

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["hud"])


@router.get("/hud/carousel")
async def hud_carousel(user_id: str = Depends(require_user_id)) -> dict:
    """Snapshot de las 7 tarjetas del carrusel CASTILLO."""
    try:
        return build_carousel_snapshot(user_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("[CAROUSEL] error: %s", exc)
        return {
            "cards": [],
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "health": {"ok": False},
            "prospection_mode": False,
            "error": "carousel_unavailable",
        }


@router.get("/health/detailed")
async def health_detailed(_user_id: str = Depends(require_user_id)) -> dict:
    """Health agregado SaaS — tarjeta SYSTEM."""
    return build_detailed_health()
