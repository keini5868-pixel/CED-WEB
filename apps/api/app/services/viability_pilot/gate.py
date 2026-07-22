"""Gate de piloto — sin header/env, el módulo no existe para callers públicos."""

from __future__ import annotations

from fastapi import Header, HTTPException, Request

from app.config import get_settings

PILOT_HEADER = "X-CED-Viability-Pilot"
PILOT_HEADER_VALUE = "1"


def viability_pilot_enabled() -> bool:
    """Env master switch. Default True so staging can use it; still needs header."""
    return bool(get_settings().viability_module_pilot)


def require_viability_pilot_header(
    x_ced_viability_pilot: str | None = Header(default=None, alias=PILOT_HEADER),
) -> None:
    if not viability_pilot_enabled():
        raise HTTPException(
            status_code=404,
            detail="Módulo de viabilidad no disponible.",
        )
    if (x_ced_viability_pilot or "").strip() != PILOT_HEADER_VALUE:
        raise HTTPException(
            status_code=404,
            detail="Módulo de viabilidad no disponible.",
        )


def request_has_viability_pilot_header(request: Request) -> bool:
    raw = request.headers.get(PILOT_HEADER) or request.headers.get(
        PILOT_HEADER.lower()
    )
    return (raw or "").strip() == PILOT_HEADER_VALUE
