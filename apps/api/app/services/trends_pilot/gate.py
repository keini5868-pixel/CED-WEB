"""Gate de piloto Tendencias."""

from __future__ import annotations

from fastapi import Header, HTTPException, Request

from app.config import get_settings

PILOT_HEADER = "X-CED-Trends-Pilot"
PILOT_HEADER_VALUE = "1"


def trends_pilot_enabled() -> bool:
    return bool(get_settings().trends_module_pilot)


def require_trends_pilot_header(
    x_ced_trends_pilot: str | None = Header(default=None, alias=PILOT_HEADER),
) -> None:
    if not trends_pilot_enabled():
        raise HTTPException(
            status_code=404,
            detail="Módulo de tendencias no disponible.",
        )
    if (x_ced_trends_pilot or "").strip() != PILOT_HEADER_VALUE:
        raise HTTPException(
            status_code=404,
            detail="Módulo de tendencias no disponible.",
        )


def request_has_trends_pilot_header(request: Request) -> bool:
    raw = request.headers.get(PILOT_HEADER) or request.headers.get(
        PILOT_HEADER.lower()
    )
    return (raw or "").strip() == PILOT_HEADER_VALUE
