"""Gate — kill-switch default OFF + solo uso vía require_super_admin en router."""

from __future__ import annotations

from fastapi import HTTPException

from app.config import get_settings


def pocket_option_module_enabled() -> bool:
    return bool(get_settings().pocket_option_module_enabled)


def require_pocket_option_module_enabled() -> None:
    if not pocket_option_module_enabled():
        raise HTTPException(
            status_code=404,
            detail="Módulo Pocket Option no disponible.",
        )
