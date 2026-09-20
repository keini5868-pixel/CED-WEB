"""Kill-switch CED Shield — DEFAULT OFF.

Activa: CED_SHIELD_ENABLED=true
Sin el flag, wallet/seal responden 404. GET /status sigue visible para el demo Lace.
No se importa desde voz, Retell, Gemini, Tavily ni Meta.
"""

from __future__ import annotations

from fastapi import HTTPException

from app.config import get_settings


def ced_shield_enabled() -> bool:
    return bool(get_settings().ced_shield_enabled)


def require_ced_shield() -> None:
    if not ced_shield_enabled():
        raise HTTPException(status_code=404, detail="CED Shield no está disponible.")
