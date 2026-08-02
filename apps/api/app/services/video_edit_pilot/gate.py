"""Gate piloto Video Edit — default OFF.

Activa con VIDEO_EDIT_MODULE_PILOT=true + header X-CED-Video-Edit-Pilot: 1.
Kill-switch: cualquier valor distinto de true → 404.
"""

from __future__ import annotations

from fastapi import Header, HTTPException

from app.config import get_settings

PILOT_HEADER = "X-CED-Video-Edit-Pilot"
PILOT_HEADER_VALUE = "1"


def video_edit_module_pilot_enabled() -> bool:
    return bool(get_settings().video_edit_module_pilot)


def require_video_edit_pilot(
    x_ced_video_edit_pilot: str | None = Header(
        default=None,
        alias=PILOT_HEADER,
    ),
) -> None:
    if not video_edit_module_pilot_enabled():
        raise HTTPException(
            status_code=404,
            detail="Módulo de edición de video no disponible.",
        )
    if (x_ced_video_edit_pilot or "").strip() != PILOT_HEADER_VALUE:
        raise HTTPException(
            status_code=404,
            detail="Módulo de edición de video no disponible.",
        )
