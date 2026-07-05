"""Módulo ambiente — Weather, Air Quality, Solar y Pollen (Google Maps Platform)."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import httpx

from app.config import get_settings
from app.modules.base_module import BaseModule
from app.services.orchestrator_types import ModuleResult
from app.services.retell_llm_types import Utterance

logger = logging.getLogger(__name__)

ENVIRONMENT_PATTERNS: tuple[str, ...] = (
    r"\b(clima|tiempo|temperatura|calor|fr[ií]o)\b",
    r"\b(va a llover|lluvia|nublado|despejado)\b",
    r"\b(calidad del aire|contaminaci[oó]n|aire)\b",
    r"\b(horas de sol|sol hoy|trabajar afuera)\b",
    r"\b(polen|alergia|al[eé]rgico)\b",
    r"\b(c[oó]mo est[aá] el tiempo|qu[eé] clima)\b",
)

_LOCATION_IN_QUERY = re.compile(
    r"\b(?:clima|tiempo|temperatura)\s+(?:en|de)\s+(.+?)(?:\?|$)",
    re.I,
)


def is_environment_intent(text: str) -> bool:
    t = (text or "").strip().lower()
    if len(t) < 4:
        return False
    return any(re.search(p, t) for p in ENVIRONMENT_PATTERNS)


def _google_maps_key() -> str:
    settings = get_settings()
    key = (settings.google_maps_api_key or settings.google_api_key or "").strip()
    if not key:
        raise ValueError("GOOGLE_MAPS_API_KEY no configurada.")
    return key


def _extract_place_from_query(text: str) -> str:
    match = _LOCATION_IN_QUERY.search(text or "")
    if match:
        return match.group(1).strip(" ?.:,")
    return ""


def resolve_environment_coordinates(user_id: str, transcript: str = "") -> tuple[float, float] | None:
    """Lat/lng desde GPS de navegación o geocodificación del lugar en la pregunta."""
    from app.services.navigation_session import get_location

    loc = get_location(user_id)
    if loc and loc.get("lat") is not None and loc.get("lng") is not None:
        return float(loc["lat"]), float(loc["lng"])

    place = _extract_place_from_query(transcript)
    if not place:
        return None

    from app.services.navigation_maps import geocode_address

    geo = geocode_address(place)
    if geo.get("ok") and geo.get("lat") is not None and geo.get("lng") is not None:
        return float(geo["lat"]), float(geo["lng"])
    return None


def _weather_condition_text(data: dict[str, Any]) -> str:
    wc = data.get("weatherCondition") or {}
    desc = wc.get("description")
    if isinstance(desc, dict):
        text = str(desc.get("text") or "").strip()
        if text:
            return text.lower()
    if isinstance(desc, str) and desc.strip():
        return desc.strip().lower()
    return str(wc.get("type") or "condiciones actuales").replace("_", " ").lower()


def _wind_kmh(data: dict[str, Any]) -> str | int | float:
    wind = data.get("wind") or {}
    speed = wind.get("speed") or {}
    if isinstance(speed, dict):
        return speed.get("value", "?")
    return speed or "?"


async def get_weather(lat: float, lng: float) -> dict[str, str]:
    url = "https://weather.googleapis.com/v1/currentConditions:lookup"
    params = {
        "key": _google_maps_key(),
        "location.latitude": lat,
        "location.longitude": lng,
        "languageCode": "es",
        "unitsSystem": "METRIC",
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        data = response.json()

    temp_obj = data.get("temperature") or {}
    temp = temp_obj.get("degrees", "?")
    condition = _weather_condition_text(data)
    humidity = data.get("relativeHumidity", "?")
    wind = _wind_kmh(data)

    return {
        "spoken": f"{temp} grados, {condition}, humedad {humidity}%, viento {wind} km/h"
    }


async def get_air_quality(lat: float, lng: float) -> dict[str, str]:
    url = "https://airquality.googleapis.com/v1/currentConditions:lookup"
    payload = {
        "location": {"latitude": lat, "longitude": lng},
        "languageCode": "es",
    }
    params = {"key": _google_maps_key()}
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(url, json=payload, params=params)
        response.raise_for_status()
        data = response.json()

    indexes = data.get("indexes") or [{}]
    aqi = indexes[0] if indexes else {}
    category = str(aqi.get("category") or aqi.get("displayName") or "desconocida")
    value = aqi.get("aqiDisplay") or aqi.get("aqi") or "?"

    return {"spoken": f"Calidad del aire {category}, índice {value}"}


async def get_solar(lat: float, lng: float) -> dict[str, str]:
    url = "https://solar.googleapis.com/v1/buildingInsights:findClosest"
    params = {
        "key": _google_maps_key(),
        "location.latitude": lat,
        "location.longitude": lng,
        "requiredQuality": "LOW",
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        data = response.json()

    solar = data.get("solarPotential") or {}
    hours_year = float(solar.get("maxSunshineHoursPerYear") or 0)
    hours_day = round(hours_year / 365, 1) if hours_year else 0

    return {"spoken": f"{hours_day} horas de sol promedio hoy"}


async def get_pollen(lat: float, lng: float) -> dict[str, str]:
    url = "https://pollen.googleapis.com/v1/forecast:lookup"
    params = {
        "key": _google_maps_key(),
        "location.latitude": lat,
        "location.longitude": lng,
        "days": 1,
        "languageCode": "es",
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        data = response.json()

    daily = (data.get("dailyInfo") or [{}])[0]
    types = daily.get("pollenTypeInfo") or []

    if not types:
        return {"spoken": "No hay datos de polen disponibles hoy"}

    results: list[str] = []
    for item in types:
        name = str(item.get("displayName") or item.get("code") or "").strip()
        index_info = item.get("indexInfo") or {}
        level = str(index_info.get("category") or index_info.get("value") or "").strip()
        if name and level:
            results.append(f"{name}: {level}")

    if not results:
        return {"spoken": "No hay datos de polen disponibles hoy"}

    return {"spoken": "Niveles de polen hoy: " + ", ".join(results)}


def _web_search_fallback(transcript: str) -> str:
    from app.services.gemini_grounded import execute_search_web_sync

    query = (transcript or "").strip() or "clima actual"
    result = execute_search_web_sync(query, kind="weather")
    summary = str(result.get("summary") or result.get("message") or "").strip()
    if result.get("ok") and summary:
        return summary
    return (
        "No pude obtener datos ambientales en este momento, señor. "
        "Intente de nuevo en unos minutos."
    )


async def handle_environment_query(
    transcript: str,
    lat: float,
    lng: float,
) -> dict[str, str]:
    t = (transcript or "").lower()
    results: list[str] = []

    if any(
        w in t
        for w in [
            "clima",
            "tiempo",
            "temperatura",
            "calor",
            "frío",
            "frio",
            "lluvia",
            "llover",
            "nublado",
            "afuera",
            "exterior",
            "trabajar",
        ]
    ):
        try:
            weather = await get_weather(lat, lng)
            results.append(weather["spoken"])
        except Exception:  # noqa: BLE001
            logger.warning("[ENV] weather failed", exc_info=True)

    if any(
        w in t
        for w in [
            "aire",
            "contaminación",
            "contaminacion",
            "calidad",
            "afuera",
            "exterior",
            "trabajar",
        ]
    ):
        try:
            air = await get_air_quality(lat, lng)
            results.append(air["spoken"])
        except Exception:  # noqa: BLE001
            logger.warning("[ENV] air quality failed", exc_info=True)

    if any(w in t for w in ["sol", "solar", "afuera", "exterior"]):
        try:
            solar = await get_solar(lat, lng)
            results.append(solar["spoken"])
        except Exception:  # noqa: BLE001
            logger.warning("[ENV] solar failed", exc_info=True)

    if any(w in t for w in ["polen", "alergia", "alérgico", "alergico"]):
        try:
            pollen = await get_pollen(lat, lng)
            results.append(pollen["spoken"])
        except Exception:  # noqa: BLE001
            logger.warning("[ENV] pollen failed", exc_info=True)

    if not results:
        try:
            weather = await get_weather(lat, lng)
            air = await get_air_quality(lat, lng)
            results = [weather["spoken"], air["spoken"]]
        except Exception:  # noqa: BLE001
            logger.warning("[ENV] default weather+air failed", exc_info=True)
            return {"spoken": _web_search_fallback(transcript)}

    spoken = "Señor, " + ". ".join(results) + "."
    if any(w in t for w in ["afuera", "exterior", "trabajar"]):
        spoken = spoken.rstrip(".") + ". Excelente día para trabajar al exterior."
    return {"spoken": spoken}


def handle_environment_query_sync(user_id: str, transcript: str) -> dict[str, str]:
    coords = resolve_environment_coordinates(user_id, transcript)
    if not coords:
        return {"spoken": _web_search_fallback(transcript)}
    lat, lng = coords
    try:
        return asyncio.run(handle_environment_query(transcript, lat, lng))
    except Exception:  # noqa: BLE001
        logger.warning("[ENV] sync query failed", exc_info=True)
        return {"spoken": _web_search_fallback(transcript)}


class EnvironmentModule(BaseModule):
    name = "environment"

    async def activate(
        self,
        transcript: str,
        *,
        user_id: str,
        call_id: str,
        user_text: str = "",
        utterances: list[Utterance] | None = None,
    ) -> ModuleResult:
        self._active = True
        return await self._run_query(user_id, user_text or transcript)

    async def handle_command(
        self,
        transcript: str,
        *,
        user_id: str,
        call_id: str,
        user_text: str = "",
        utterances: list[Utterance] | None = None,
    ) -> ModuleResult:
        if is_environment_intent(user_text or transcript):
            return await self._run_query(user_id, user_text or transcript)
        return self._idle()

    async def _run_query(self, user_id: str, text: str) -> ModuleResult:
        coords = resolve_environment_coordinates(user_id, text)
        if not coords:
            spoken = _web_search_fallback(text)
            return ModuleResult(ok=False, spoken=spoken, handles_response=True)

        lat, lng = coords
        try:
            result = await handle_environment_query(text, lat, lng)
            spoken = str(result.get("spoken") or "").strip()
            if not spoken:
                spoken = _web_search_fallback(text)
            return ModuleResult(ok=True, spoken=spoken, handles_response=True)
        except Exception:  # noqa: BLE001
            logger.exception("[ENV] module query failed user=%s", user_id[:8])
            return ModuleResult(
                ok=False,
                spoken=_web_search_fallback(text),
                handles_response=True,
            )
