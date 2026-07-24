"""Gate de producción — módulo Tendencias.

Kill-switch: TRENDS_MODULE_ENABLED=false → 404.
Auth: require_user_id en el router (usuarios logueados).
Sin header de piloto.
"""

from __future__ import annotations

from fastapi import HTTPException

from app.config import get_settings


def trends_module_enabled() -> bool:
    return bool(get_settings().trends_module_enabled)


def require_trends_module_enabled() -> None:
    if not trends_module_enabled():
        raise HTTPException(
            status_code=404,
            detail="Módulo de tendencias no disponible.",
        )


# Compat aliases (pre-graduation names)
def trends_pilot_enabled() -> bool:
    return trends_module_enabled()


def require_trends_pilot_header() -> None:
    require_trends_module_enabled()
