"""Gate de piloto Oportunidades."""

from __future__ import annotations

from fastapi import Header, HTTPException, Request

from app.config import get_settings

PILOT_HEADER = "X-CED-Opportunities-Pilot"
PILOT_HEADER_VALUE = "1"


def opportunities_pilot_enabled() -> bool:
    return bool(get_settings().opportunities_module_pilot)


def require_opportunities_pilot_header(
    x_ced_opportunities_pilot: str | None = Header(
        default=None, alias=PILOT_HEADER
    ),
) -> None:
    if not opportunities_pilot_enabled():
        raise HTTPException(
            status_code=404,
            detail="Módulo de oportunidades no disponible.",
        )
    if (x_ced_opportunities_pilot or "").strip() != PILOT_HEADER_VALUE:
        raise HTTPException(
            status_code=404,
            detail="Módulo de oportunidades no disponible.",
        )


def request_has_opportunities_pilot_header(request: Request) -> bool:
    raw = request.headers.get(PILOT_HEADER) or request.headers.get(
        PILOT_HEADER.lower()
    )
    return (raw or "").strip() == PILOT_HEADER_VALUE
