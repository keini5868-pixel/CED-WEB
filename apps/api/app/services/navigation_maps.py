"""Geocodificación y rutas — Google Maps Directions / Geocoding."""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import quote

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
_DIRECTIONS_URL = "https://maps.googleapis.com/maps/api/directions/json"


def _maps_key() -> str:
    key = get_settings().google_api_key.strip()
    if not key:
        raise ValueError("GOOGLE_API_KEY no configurada para navegación.")
    return key


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def decode_polyline(encoded: str) -> list[dict[str, float]]:
    """Decodifica polyline de Google Directions."""
    if not encoded:
        return []
    points: list[dict[str, float]] = []
    index = 0
    lat = 0
    lng = 0
    length = len(encoded)
    while index < length:
        shift = 0
        result = 0
        while True:
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        dlat = ~(result >> 1) if result & 1 else result >> 1
        lat += dlat

        shift = 0
        result = 0
        while True:
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        dlng = ~(result >> 1) if result & 1 else result >> 1
        lng += dlng

        points.append({"lat": lat / 1e5, "lng": lng / 1e5})
    return points


def geocode_address(query: str, *, bias_lat: float | None = None, bias_lng: float | None = None) -> dict[str, Any]:
    q = (query or "").strip()
    if not q:
        return {"ok": False, "error": "Dirección vacía"}

    params: dict[str, str] = {"address": q, "key": _maps_key(), "language": "es"}
    if bias_lat is not None and bias_lng is not None:
        params["location"] = f"{bias_lat},{bias_lng}"

    try:
        with httpx.Client(timeout=20.0) as client:
            res = client.get(_GEOCODE_URL, params=params)
            data = res.json()
    except Exception as exc:  # noqa: BLE001
        logger.exception("[NAV] geocode failed")
        return {"ok": False, "error": str(exc)}

    if data.get("status") != "OK" or not data.get("results"):
        return {
            "ok": False,
            "error": f"No encontré esa dirección ({data.get('status', 'ZERO_RESULTS')}).",
        }

    top = data["results"][0]
    loc = top["geometry"]["location"]
    return {
        "ok": True,
        "formatted_address": top.get("formatted_address") or q,
        "lat": float(loc["lat"]),
        "lng": float(loc["lng"]),
        "place_id": top.get("place_id"),
    }


def compute_route(
    *,
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
    dest_label: str = "",
) -> dict[str, Any]:
    params = {
        "origin": f"{origin_lat},{origin_lng}",
        "destination": f"{dest_lat},{dest_lng}",
        "mode": "driving",
        "language": "es",
        "key": _maps_key(),
    }
    try:
        with httpx.Client(timeout=25.0) as client:
            res = client.get(_DIRECTIONS_URL, params=params)
            data = res.json()
    except Exception as exc:  # noqa: BLE001
        logger.exception("[NAV] directions failed")
        return {"ok": False, "error": str(exc)}

    if data.get("status") != "OK" or not data.get("routes"):
        return {
            "ok": False,
            "error": f"No pude calcular la ruta ({data.get('status', 'ZERO_RESULTS')}).",
        }

    route = data["routes"][0]
    leg = route["legs"][0]
    encoded = route.get("overview_polyline", {}).get("points") or ""
    path = decode_polyline(encoded)

    steps_out: list[dict[str, Any]] = []
    for step in leg.get("steps") or []:
        end = step.get("end_location") or {}
        start = step.get("start_location") or {}
        maneuver = step.get("maneuver") or "straight"
        steps_out.append(
            {
                "instruction": _strip_html(str(step.get("html_instructions") or "")),
                "distance_m": int((step.get("distance") or {}).get("value") or 0),
                "duration_s": int((step.get("duration") or {}).get("value") or 0),
                "maneuver": maneuver,
                "start": {"lat": float(start.get("lat", 0)), "lng": float(start.get("lng", 0))},
                "end": {"lat": float(end.get("lat", 0)), "lng": float(end.get("lng", 0))},
            }
        )

    return {
        "ok": True,
        "destination": {
            "label": dest_label or leg.get("end_address") or "Destino",
            "lat": dest_lat,
            "lng": dest_lng,
        },
        "distance_text": str((leg.get("distance") or {}).get("text") or ""),
        "duration_text": str((leg.get("duration") or {}).get("text") or ""),
        "distance_m": int((leg.get("distance") or {}).get("value") or 0),
        "duration_s": int((leg.get("duration") or {}).get("value") or 0),
        "path": path,
        "steps": steps_out,
    }
