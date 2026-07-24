"""Gate de producción — módulo Viabilidad.

Kill-switch: VIABILITY_MODULE_ENABLED=false → 404.
Auth: require_user_id en el router (usuarios logueados).
Sin header de piloto.
"""

from __future__ import annotations

from fastapi import HTTPException

from app.config import get_settings


def viability_module_enabled() -> bool:
    return bool(get_settings().viability_module_enabled)


def require_viability_module_enabled() -> None:
    if not viability_module_enabled():
        raise HTTPException(
            status_code=404,
            detail="Módulo de viabilidad no disponible.",
        )


# Compat aliases (pre-graduation names)
def viability_pilot_enabled() -> bool:
    return viability_module_enabled()


def require_viability_pilot_header() -> None:
    require_viability_module_enabled()
