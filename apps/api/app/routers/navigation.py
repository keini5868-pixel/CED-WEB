"""Navegación — GPS, rutas y estado para modo conducir."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.deps.auth import require_user_id
from app.services import navigation_maps as maps_svc
from app.services import navigation_session as nav_session

router = APIRouter(prefix="/v1/navigation", tags=["navigation"])


class LocationBody(BaseModel):
    lat: float
    lng: float
    heading: float | None = None
    speed: float | None = None
    accuracy: float | None = None


class GeocodeBody(BaseModel):
    query: str = Field(min_length=2, max_length=500)


class RouteBody(BaseModel):
    destination: str = Field(min_length=2, max_length=500)
    origin_lat: float | None = None
    origin_lng: float | None = None


class NearbyBody(BaseModel):
    query: str = Field(min_length=2, max_length=200)


class StartOptionBody(BaseModel):
    index: int = Field(ge=0, le=4)


class AckActionBody(BaseModel):
    action_id: int


@router.get("/state")
async def navigation_state(
    user_id: str = Depends(require_user_id),
    consume: bool = False,
) -> dict[str, Any]:
    return {"ok": True, **nav_session.get_state(user_id, consume_action=consume)}


@router.post("/location")
async def navigation_location(
    body: LocationBody,
    user_id: str = Depends(require_user_id),
) -> dict[str, bool]:
    nav_session.update_location(
        user_id,
        lat=body.lat,
        lng=body.lng,
        heading=body.heading,
        speed=body.speed,
        accuracy=body.accuracy,
    )
    return {"ok": True}


@router.post("/geocode")
async def navigation_geocode(
    body: GeocodeBody,
    user_id: str = Depends(require_user_id),
) -> dict[str, Any]:
    loc = nav_session.get_location(user_id)
    bias_lat = float(loc["lat"]) if loc else None
    bias_lng = float(loc["lng"]) if loc else None
    result = maps_svc.geocode_address(
        body.query,
        bias_lat=bias_lat,
        bias_lng=bias_lng,
    )
    if not result.get("ok"):
        return result
    nav_session.push_client_action(
        user_id,
        "show_destination",
        {
            "lat": result["lat"],
            "lng": result["lng"],
            "label": result.get("formatted_address") or body.query,
        },
    )
    return result


@router.post("/route")
async def navigation_route(
    body: RouteBody,
    user_id: str = Depends(require_user_id),
) -> dict[str, Any]:
    geo = maps_svc.geocode_address(body.destination)
    if not geo.get("ok"):
        return geo

    origin_lat = body.origin_lat
    origin_lng = body.origin_lng
    if origin_lat is None or origin_lng is None:
        loc = nav_session.get_location(user_id)
        if not loc:
            return {
                "ok": False,
                "error": "No tengo tu ubicación GPS. Abre el modo mapa y activa ubicación.",
            }
        origin_lat = float(loc["lat"])
        origin_lng = float(loc["lng"])

    route = maps_svc.compute_route(
        origin_lat=origin_lat,
        origin_lng=origin_lng,
        dest_lat=float(geo["lat"]),
        dest_lng=float(geo["lng"]),
        dest_label=str(geo.get("formatted_address") or body.destination),
    )
    if not route.get("ok"):
        return route

    nav_session.set_route(user_id, route)
    nav_session.push_client_action(user_id, "apply_route", route)
    return route


@router.post("/nearby")
async def navigation_nearby(
    body: NearbyBody,
    user_id: str = Depends(require_user_id),
) -> dict[str, Any]:
    loc = nav_session.get_location(user_id)
    if not loc:
        return {
            "ok": False,
            "error": "No tengo tu ubicación GPS. Abre el modo mapa y activa ubicación.",
        }
    result = maps_svc.search_nearby_places(
        body.query,
        origin_lat=float(loc["lat"]),
        origin_lng=float(loc["lng"]),
        limit=3,
    )
    if not result.get("ok"):
        return result
    nav_session.set_place_options(
        user_id,
        list(result.get("places") or []),
        query=str(result.get("query") or body.query),
    )
    nav_session.push_client_action(
        user_id,
        "show_place_options",
        {
            "query": result.get("query") or body.query,
            "places": result.get("places") or [],
        },
    )
    return result


@router.get("/suggest")
async def navigation_suggest(
    q: str = Query(min_length=2, max_length=200),
    user_id: str = Depends(require_user_id),
) -> dict[str, Any]:
    """Sugerencias de direcciones vía Geocoding (sin Places API en el cliente)."""
    loc = nav_session.get_location(user_id)
    bias_lat = float(loc["lat"]) if loc else None
    bias_lng = float(loc["lng"]) if loc else None
    if bias_lat is None or bias_lng is None:
        geo = maps_svc.geocode_address(q)
        if not geo.get("ok"):
            return {"ok": False, "suggestions": []}
        return {
            "ok": True,
            "suggestions": [
                {
                    "label": geo.get("formatted_address") or q,
                    "address": geo.get("formatted_address") or q,
                    "lat": geo["lat"],
                    "lng": geo["lng"],
                }
            ],
        }
    found = maps_svc.search_nearby_places(
        q,
        origin_lat=bias_lat,
        origin_lng=bias_lng,
        limit=5,
    )
    if not found.get("ok"):
        geo = maps_svc.geocode_address(q, bias_lat=bias_lat, bias_lng=bias_lng)
        if not geo.get("ok"):
            return {"ok": False, "suggestions": []}
        return {
            "ok": True,
            "suggestions": [
                {
                    "label": geo.get("formatted_address") or q,
                    "address": geo.get("formatted_address") or q,
                    "lat": geo["lat"],
                    "lng": geo["lng"],
                }
            ],
        }
    suggestions = [
        {
            "label": str(p.get("name") or p.get("address") or q),
            "address": str(p.get("address") or ""),
            "lat": p["lat"],
            "lng": p["lng"],
        }
        for p in found.get("places") or []
    ]
    return {"ok": True, "suggestions": suggestions}


@router.post("/start-option")
async def navigation_start_option(
    body: StartOptionBody,
    user_id: str = Depends(require_user_id),
) -> dict[str, Any]:
    options = nav_session.get_place_options(user_id)
    if not options or body.index >= len(options):
        return {"ok": False, "error": "No hay opción de destino pendiente."}
    loc = nav_session.get_location(user_id)
    if not loc:
        return {
            "ok": False,
            "error": "No tengo tu ubicación GPS. Active ubicación en el mapa.",
        }
    place = options[body.index]
    route = maps_svc.compute_route(
        origin_lat=float(loc["lat"]),
        origin_lng=float(loc["lng"]),
        dest_lat=float(place["lat"]),
        dest_lng=float(place["lng"]),
        dest_label=str(place.get("name") or place.get("address") or "Destino"),
    )
    if not route.get("ok"):
        return route
    nav_session.set_route(user_id, route)
    nav_session.clear_place_options(user_id)
    nav_session.push_client_action(user_id, "apply_route", route)
    return route


@router.post("/cancel")
async def navigation_cancel(user_id: str = Depends(require_user_id)) -> dict[str, bool]:
    nav_session.clear_navigation(user_id)
    nav_session.push_client_action(user_id, "cancel_navigation", {})
    return {"ok": True}


@router.post("/ack-action")
async def navigation_ack_action(
    body: AckActionBody,
    user_id: str = Depends(require_user_id),
) -> dict[str, bool]:
    nav_session.consume_client_action(user_id, body.action_id)
    return {"ok": True}
