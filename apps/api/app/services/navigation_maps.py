"""Geocodificación, Places y rutas — Google Maps."""

from __future__ import annotations

import logging
import math
import re
from typing import Any, Callable

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
_DIRECTIONS_URL = "https://maps.googleapis.com/maps/api/directions/json"
_ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
_ROUTES_FIELD_MASK = (
    "routes.duration,routes.distanceMeters,routes.polyline.encodedPolyline,"
    "routes.legs.steps.navigationInstruction,routes.legs.steps.distanceMeters,"
    "routes.legs.steps.staticDuration,routes.legs.steps.startLocation,"
    "routes.legs.steps.endLocation,routes.legs.localizedValues,"
    "routes.legs.distanceMeters,routes.legs.duration"
)
_PLACES_TEXT_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
_PLACES_NEW_URL = "https://places.googleapis.com/v1/places:searchText"

_PLACES_DENIED = frozenset(
    {
        "REQUEST_DENIED",
        "PERMISSION_DENIED",
        "INVALID_REQUEST",
        "API_KEY_INVALID",
    }
)


def _maps_key() -> str:
    settings = get_settings()
    key = (settings.google_maps_api_key or settings.google_api_key or "").strip()
    if not key:
        raise ValueError("GOOGLE_MAPS_API_KEY no configurada para navegación.")
    return key


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlng / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def format_distance_imperial(meters: float) -> str:
    miles = meters / 1609.344
    if miles < 0.2:
        feet = meters * 3.28084
        return f"{int(feet)} ft"
    return f"{miles:.1f} mi"


def _place_name_from_geocode(row: dict[str, Any], query: str) -> str:
    for comp in row.get("address_components") or []:
        if "establishment" in (comp.get("types") or []):
            return str(comp.get("long_name") or comp.get("short_name") or query)
    formatted = str(row.get("formatted_address") or query)
    return formatted.split(",")[0].strip() or query


def _build_place_row(
    *,
    name: str,
    address: str,
    lat: float,
    lng: float,
    origin_lat: float,
    origin_lng: float,
    place_id: str = "",
    rating: float | None = None,
    rating_count: int | None = None,
    phone: str = "",
    category: str = "",
    open_now: bool | None = None,
    hours_text: str = "",
) -> dict[str, Any]:
    dist_m = _haversine_m(origin_lat, origin_lng, lat, lng)
    row: dict[str, Any] = {
        "name": name,
        "address": address,
        "lat": lat,
        "lng": lng,
        "place_id": place_id,
        "distance_m": int(dist_m),
        "distance_text": format_distance_imperial(dist_m),
    }
    if rating is not None:
        row["rating"] = round(float(rating), 1)
    if rating_count is not None:
        row["rating_count"] = int(rating_count)
    if phone:
        row["phone"] = phone
    if category:
        row["category"] = category
    if open_now is not None:
        row["open_now"] = open_now
    if hours_text:
        row["hours_text"] = hours_text
    return row


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


def geocode_address(
    query: str,
    *,
    bias_lat: float | None = None,
    bias_lng: float | None = None,
) -> dict[str, Any]:
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

    status = str(data.get("status") or "")
    if status != "OK" or not data.get("results"):
        return {
            "ok": False,
            "error": f"No encontré esa dirección ({status or 'ZERO_RESULTS'}).",
            "status": status,
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


def _search_via_geocode(
    query: str,
    *,
    origin_lat: float,
    origin_lng: float,
    limit: int,
    radius_m: int,
) -> dict[str, Any]:
    """Geocoding API con sesgo de ubicación — no requiere Places API."""
    params: dict[str, str] = {
        "address": query,
        "key": _maps_key(),
        "language": "es",
        "location": f"{origin_lat},{origin_lng}",
    }
    try:
        with httpx.Client(timeout=20.0) as client:
            res = client.get(_GEOCODE_URL, params=params)
            data = res.json()
    except Exception as exc:  # noqa: BLE001
        logger.exception("[NAV] geocode places search failed")
        return {"ok": False, "error": str(exc)}

    status = str(data.get("status") or "")
    if status != "OK" or not data.get("results"):
        return {
            "ok": False,
            "error": f"No encontré {query} cerca ({status or 'ZERO_RESULTS'}).",
            "status": status,
        }

    places: list[dict[str, Any]] = []
    for row in data.get("results") or []:
        loc = (row.get("geometry") or {}).get("location") or {}
        lat = float(loc.get("lat", 0))
        lng = float(loc.get("lng", 0))
        if not lat and not lng:
            continue
        dist_m = _haversine_m(origin_lat, origin_lng, lat, lng)
        if dist_m > radius_m:
            continue
        address = str(row.get("formatted_address") or "")
        name = _place_name_from_geocode(row, query)
        places.append(
            _build_place_row(
                name=name,
                address=address,
                lat=lat,
                lng=lng,
                origin_lat=origin_lat,
                origin_lng=origin_lng,
                place_id=str(row.get("place_id") or ""),
            )
        )

    if not places:
        return {"ok": False, "error": f"No encontré {query} cerca.", "status": status}

    places.sort(key=lambda p: int(p.get("distance_m") or 0))
    return {"ok": True, "query": query, "places": places[:limit], "source": "geocode"}


def _search_via_places_legacy(
    query: str,
    *,
    origin_lat: float,
    origin_lng: float,
    limit: int,
    radius_m: int,
) -> dict[str, Any]:
    params = {
        "query": query,
        "location": f"{origin_lat},{origin_lng}",
        "radius": str(radius_m),
        "key": _maps_key(),
        "language": "es",
    }
    try:
        with httpx.Client(timeout=20.0) as client:
            res = client.get(_PLACES_TEXT_URL, params=params)
            data = res.json()
    except Exception as exc:  # noqa: BLE001
        logger.exception("[NAV] legacy places search failed")
        return {"ok": False, "error": str(exc)}

    status = str(data.get("status") or "")
    if status in _PLACES_DENIED:
        logger.warning("[NAV] legacy Places API denied (%s) — probando fallback", status)
        return {"ok": False, "error": status, "status": status}

    if status not in {"OK", "ZERO_RESULTS"} or not data.get("results"):
        return {
            "ok": False,
            "error": f"No encontré {query} cerca ({status or 'ZERO_RESULTS'}).",
            "status": status,
        }

    places: list[dict[str, Any]] = []
    for row in data["results"][: max(1, min(limit, 5))]:
        loc = (row.get("geometry") or {}).get("location") or {}
        lat = float(loc.get("lat", 0))
        lng = float(loc.get("lng", 0))
        if not lat and not lng:
            continue
        places.append(
            _build_place_row(
                name=str(row.get("name") or query),
                address=str(row.get("formatted_address") or ""),
                lat=lat,
                lng=lng,
                origin_lat=origin_lat,
                origin_lng=origin_lng,
                place_id=str(row.get("place_id") or ""),
            )
        )

    if not places:
        return {"ok": False, "error": f"No encontré {query} cerca.", "status": status}

    places.sort(key=lambda p: int(p.get("distance_m") or 0))
    return {"ok": True, "query": query, "places": places[:limit], "source": "places_legacy"}


def _search_via_places_new(
    query: str,
    *,
    origin_lat: float,
    origin_lng: float,
    limit: int,
    radius_m: int,
) -> dict[str, Any]:
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": _maps_key(),
        "X-Goog-FieldMask": (
            "places.displayName,places.formattedAddress,places.location,places.id,"
            "places.rating,places.userRatingCount,places.nationalPhoneNumber,"
            "places.primaryTypeDisplayName,places.currentOpeningHours"
        ),
    }
    body = {
        "textQuery": query,
        "languageCode": "es",
        "locationBias": {
            "circle": {
                "center": {"latitude": origin_lat, "longitude": origin_lng},
                "radius": float(radius_m),
            }
        },
        "maxResultCount": max(1, min(limit, 5)),
    }
    try:
        with httpx.Client(timeout=20.0) as client:
            res = client.post(_PLACES_NEW_URL, headers=headers, json=body)
            if res.status_code in {403, 401}:
                logger.warning(
                    "[NAV] Places API (New) HTTP %s — probando fallback",
                    res.status_code,
                )
                return {"ok": False, "error": "REQUEST_DENIED", "status": "REQUEST_DENIED"}
            data = res.json()
    except Exception as exc:  # noqa: BLE001
        logger.exception("[NAV] Places API (New) search failed")
        return {"ok": False, "error": str(exc)}

    if data.get("error"):
        err_status = str((data.get("error") or {}).get("status") or "REQUEST_DENIED")
        if err_status in _PLACES_DENIED:
            logger.warning("[NAV] Places API (New) denied (%s) — probando fallback", err_status)
        return {"ok": False, "error": err_status, "status": err_status}

    rows = data.get("places") or []
    if not rows:
        return {"ok": False, "error": f"No encontré {query} cerca.", "status": "ZERO_RESULTS"}

    places: list[dict[str, Any]] = []
    for row in rows:
        loc = row.get("location") or {}
        lat = float(loc.get("latitude", 0))
        lng = float(loc.get("longitude", 0))
        if not lat and not lng:
            continue
        display = row.get("displayName") or {}
        name = str(display.get("text") or query)
        address = str(row.get("formattedAddress") or name)
        category_row = row.get("primaryTypeDisplayName") or {}
        category = str(category_row.get("text") or "").strip()
        hours = row.get("currentOpeningHours") or {}
        open_now = hours.get("openNow")
        hours_text = ""
        if open_now is True:
            close_raw = str(hours.get("nextCloseTime") or "")
            if close_raw:
                try:
                    from datetime import datetime

                    close_dt = datetime.fromisoformat(close_raw.replace("Z", "+00:00"))
                    hour = close_dt.hour % 12 or 12
                    suffix = "a. m." if close_dt.hour < 12 else "p. m."
                    hours_text = f"Cierra a las {hour}:{close_dt.minute:02d} {suffix}"
                except ValueError:
                    hours_text = "Cierra pronto"
        rating = row.get("rating")
        rating_count = row.get("userRatingCount")
        phone = str(row.get("nationalPhoneNumber") or "").strip()
        places.append(
            _build_place_row(
                name=name,
                address=address,
                lat=lat,
                lng=lng,
                origin_lat=origin_lat,
                origin_lng=origin_lng,
                place_id=str(row.get("id") or ""),
                rating=float(rating) if rating is not None else None,
                rating_count=int(rating_count) if rating_count is not None else None,
                phone=phone,
                category=category,
                open_now=open_now if isinstance(open_now, bool) else None,
                hours_text=hours_text,
            )
        )

    if not places:
        return {"ok": False, "error": f"No encontré {query} cerca.", "status": "ZERO_RESULTS"}

    places.sort(key=lambda p: int(p.get("distance_m") or 0))
    return {"ok": True, "query": query, "places": places[:limit], "source": "places_new"}


def _search_query_variants(query: str) -> list[str]:
    """Genera variantes más cortas cuando el nombre completo no devuelve resultados."""
    q = (query or "").strip()
    if not q:
        return []
    variants: list[str] = [q]
    lower = q.lower()
    for suffix in (
        " neighborhood market",
        " supercenter",
        " supermarket",
        " store",
        " market",
        " express",
    ):
        idx = lower.find(suffix)
        if idx > 0:
            short = q[:idx].strip()
            if short and short not in variants:
                variants.append(short)
    words = q.split()
    if len(words) >= 2:
        head = words[0].strip()
        if len(head) >= 3 and head.lower() not in {"the", "los", "las", "una", "un"}:
            if head not in variants:
                variants.append(head)
    return variants


def search_nearby_places(
    query: str,
    *,
    origin_lat: float,
    origin_lng: float,
    limit: int = 3,
    radius_m: int = 50_000,
) -> dict[str, Any]:
    """Busca lugares cercanos: Places (New) → Places legacy → Geocoding."""
    q = (query or "").strip()
    if not q:
        return {"ok": False, "error": "Indique qué lugar buscar."}

    search_fns: list[tuple[str, Callable[..., dict[str, Any]]]] = [
        ("places_new", _search_via_places_new),
        ("places_legacy", _search_via_places_legacy),
        ("geocode", _search_via_geocode),
    ]
    last_error = "No encontré resultados cerca."
    for variant in _search_query_variants(q):
        for source, fn in search_fns:
            result = fn(
                variant,
                origin_lat=origin_lat,
                origin_lng=origin_lng,
                limit=limit,
                radius_m=radius_m,
            )
            if result.get("ok"):
                logger.info(
                    "[NAV] nearby search ok source=%s query=%r variant=%r",
                    source,
                    q[:40],
                    variant[:40],
                )
                result["query"] = q
                return result
            last_error = str(result.get("error") or last_error)
            status = str(result.get("status") or "")
            if status in _PLACES_DENIED or source != "geocode":
                logger.info(
                    "[NAV] nearby search fallback from %s status=%s variant=%r",
                    source,
                    status,
                    variant[:40],
                )
                continue
            break

    return {"ok": False, "error": last_error}


def _format_duration_text(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} min"
    mins = max(1, round(seconds / 60))
    return f"{mins} min"


def _compute_route_directions_legacy(
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
        "source": "directions_legacy",
    }


def _compute_route_routes_api(
    *,
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
    dest_label: str = "",
) -> dict[str, Any]:
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": _maps_key(),
        "X-Goog-FieldMask": _ROUTES_FIELD_MASK,
    }
    body = {
        "origin": {
            "location": {"latLng": {"latitude": origin_lat, "longitude": origin_lng}}
        },
        "destination": {
            "location": {"latLng": {"latitude": dest_lat, "longitude": dest_lng}}
        },
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE",
        "languageCode": "es",
        "units": "IMPERIAL",
        "computeAlternativeRoutes": False,
        "routeModifiers": {"avoidTolls": False},
    }
    try:
        with httpx.Client(timeout=25.0) as client:
            res = client.post(_ROUTES_URL, headers=headers, json=body)
            data = res.json()
    except Exception as exc:  # noqa: BLE001
        logger.exception("[NAV] Routes API failed")
        return {"ok": False, "error": str(exc)}

    if res.status_code >= 400 or data.get("error"):
        err = data.get("error") or {}
        msg = str(err.get("message") or err.get("status") or res.status_code)
        logger.warning("[NAV] Routes API error: %s", msg[:120])
        return {"ok": False, "error": msg}

    routes = data.get("routes") or []
    if not routes:
        return {"ok": False, "error": "No pude calcular la ruta (ZERO_RESULTS)."}

    route = routes[0]
    leg = (route.get("legs") or [{}])[0]
    encoded = (route.get("polyline") or {}).get("encodedPolyline") or ""
    path = decode_polyline(encoded)

    localized = leg.get("localizedValues") or {}
    distance_text = str((localized.get("distance") or {}).get("text") or "")
    duration_text = str((localized.get("duration") or {}).get("text") or "")
    distance_m = int(route.get("distanceMeters") or leg.get("distanceMeters") or 0)
    duration_raw = str(route.get("duration") or leg.get("duration") or "0s")
    duration_s = int(duration_raw.rstrip("s") or 0)

    if not distance_text and distance_m:
        distance_text = _format_distance_text(distance_m)
    if not duration_text and duration_s:
        duration_text = _format_duration_text(duration_s)

    steps_out: list[dict[str, Any]] = []
    for step in leg.get("steps") or []:
        nav = step.get("navigationInstruction") or {}
        instruction = str(nav.get("instructions") or nav.get("instruction") or "").strip()
        start = step.get("startLocation") or {}
        end = step.get("endLocation") or {}
        start_lat = (start.get("latLng") or {}).get("latitude")
        start_lng = (start.get("latLng") or {}).get("longitude")
        end_lat = (end.get("latLng") or {}).get("latitude")
        end_lng = (end.get("latLng") or {}).get("longitude")
        static_duration = str(step.get("staticDuration") or "0s")
        step_duration_s = int(static_duration.rstrip("s") or 0)
        steps_out.append(
            {
                "instruction": instruction or "Continúe por la ruta",
                "distance_m": int(step.get("distanceMeters") or 0),
                "duration_s": step_duration_s,
                "maneuver": str(nav.get("maneuver") or "straight"),
                "start": {
                    "lat": float(start_lat or origin_lat),
                    "lng": float(start_lng or origin_lng),
                },
                "end": {
                    "lat": float(end_lat or dest_lat),
                    "lng": float(end_lng or dest_lng),
                },
            }
        )

    return {
        "ok": True,
        "destination": {
            "label": dest_label or "Destino",
            "lat": dest_lat,
            "lng": dest_lng,
        },
        "distance_text": distance_text,
        "duration_text": duration_text,
        "distance_m": distance_m,
        "duration_s": duration_s,
        "path": path,
        "steps": steps_out,
        "source": "routes_api",
    }


def compute_route(
    *,
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
    dest_label: str = "",
) -> dict[str, Any]:
    routes_result = _compute_route_routes_api(
        origin_lat=origin_lat,
        origin_lng=origin_lng,
        dest_lat=dest_lat,
        dest_lng=dest_lng,
        dest_label=dest_label,
    )
    if routes_result.get("ok"):
        logger.info("[NAV] route ok source=routes_api dest=%s", dest_label[:40])
        return routes_result

    logger.info(
        "[NAV] Routes API fallback to Directions legacy: %s",
        str(routes_result.get("error") or "")[:80],
    )
    return _compute_route_directions_legacy(
        origin_lat=origin_lat,
        origin_lng=origin_lng,
        dest_lat=dest_lat,
        dest_lng=dest_lng,
        dest_label=dest_label,
    )
