"""Gate de producción — módulo Oportunidades.

Kill-switch: OPPORTUNITIES_MODULE_ENABLED=false → 404.
Auth: require_user_id en el router (usuarios logueados).
Sin header de piloto.
"""

from __future__ import annotations

from fastapi import HTTPException

from app.config import get_settings


def opportunities_module_enabled() -> bool:
    return bool(get_settings().opportunities_module_enabled)


def require_opportunities_module_enabled() -> None:
    if not opportunities_module_enabled():
        raise HTTPException(
            status_code=404,
            detail="Módulo de oportunidades no disponible.",
        )
