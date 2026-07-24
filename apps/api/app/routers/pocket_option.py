"""API admin — monitoreo Pocket Option (demo). Solo lectura en v1."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.deps.auth import require_super_admin
from app.services.pocket_option.gate import require_pocket_option_module_enabled
from app.services.pocket_option.service import status_snapshot

router = APIRouter(
    prefix="/v1/admin/pocket-option",
    tags=["admin-pocket-option"],
)


@router.get("/status")
async def pocket_option_status(
    _admin_id: str = Depends(require_super_admin),
) -> dict:
    """Estado del worker + trades. 404 si kill-switch OFF."""
    require_pocket_option_module_enabled()
    return status_snapshot()
