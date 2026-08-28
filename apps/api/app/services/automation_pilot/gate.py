"""Gate módulo Automatización — DEFAULT OFF.

Kill-switch: AUTOMATION_MODULE_ENABLED=true para API.
IG/FB live: AUTOMATION_IG_FB_LIVE_ENABLED=true (si OFF → dry-run).
Header piloto: X-CED-Automation-Pilot: 1 en rutas autenticadas.
"""

from __future__ import annotations

from fastapi import Header, HTTPException

from app.config import get_settings

PILOT_HEADER = "X-CED-Automation-Pilot"
PILOT_HEADER_VALUE = "1"


def automation_module_enabled() -> bool:
    return bool(get_settings().automation_module_enabled)


def automation_ig_fb_live_enabled() -> bool:
    """Si False, IG/FB solo registran eventos (dry-run) sin envíos reales."""
    return bool(get_settings().automation_ig_fb_live_enabled)


def require_automation_module(
    x_ced_automation_pilot: str | None = Header(
        default=None,
        alias=PILOT_HEADER,
    ),
) -> None:
    if not automation_module_enabled():
        raise HTTPException(
            status_code=404,
            detail="Módulo Automatización no disponible.",
        )
    if (x_ced_automation_pilot or "").strip() != PILOT_HEADER_VALUE:
        raise HTTPException(
            status_code=404,
            detail="Módulo Automatización no disponible.",
        )
