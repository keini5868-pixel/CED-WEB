"""HUD Life dashboard — clima, aire y polen."""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

try:
    from zoneinfo import ZoneInfo

    _TZ = ZoneInfo("America/New_York")
except Exception:  # noqa: BLE001
    _TZ = timezone(timedelta(hours=-4))

_DAYS_ES = (
    "Lunes",
    "Martes",
    "Miércoles",
    "Jueves",
    "Viernes",
    "Sábado",
    "Domingo",
)
_MONTHS_ES = (
    "Enero",
    "Febrero",
    "Marzo",
    "Abril",
    "Mayo",
    "Junio",
    "Julio",
    "Agosto",
    "Septiembre",
    "Octubre",
    "Noviembre",
    "Diciembre",
)
_DEFAULT_PLACE = "Charlotte NC"
_WEATHER_CACHE_TTL = timedelta(minutes=30)
_WEATHER_CACHE: dict[str, dict[str, Any]] = {}


def clean_life_text(text: str) -> str:
    """Quita artefactos [cite...] de resúmenes web."""
    cleaned = str(text or "")
    cleaned = re.sub(r"\[cite[^\]]*\]", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\[cite\s*", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\[cite\s*$", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\[\d+\]", "", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip()


def _date_label() -> str:
    now = datetime.now(_TZ)
    day = _DAYS_ES[now.weekday()]
    month = _MONTHS_ES[now.month - 1]
    return f"{day} {now.day} de {month}, {now.year}"


def _web_lines(query: str, *, kind: str = "weather") -> list[str]:
    from app.services.gemini_grounded import execute_search_web_sync

    result = execute_search_web_sync(query, kind=kind)
    summary = clean_life_text(
        str(result.get("summary") or result.get("message") or "").strip()
    )
    if not summary:
        return []
    parts = [
        clean_life_text(p.strip())
        for p in summary.replace("·", ".").split(".")
        if clean_life_text(p.strip())
    ]
    if parts:
        return parts[:4]
    return [summary[:240]]


def _safe_web_lines(
    query: str,
    fallback: str,
    *,
    kind: str = "weather",
) -> list[str]:
    try:
        lines = _web_lines(query, kind=kind)
        if lines:
            return lines
    except Exception:  # noqa: BLE001
        logger.warning("[LIFE] web search failed query=%s", query[:80], exc_info=True)
    return [fallback]


def _fetch_web_sections(place: str) -> tuple[list[str], list[str], list[str]]:
    tasks: dict[str, tuple[str, str, str]] = {
        "weather": (
            f"temperatura clima {place} hoy",
            "Clima no disponible.",
            "weather",
        ),
        "air": (
            f"calidad del aire {place} hoy",
            "Calidad del aire no disponible.",
            "general",
        ),
        "pollen": (
            f"niveles de polen {place} hoy",
            "Polen no disponible.",
            "general",
        ),
    }
    results: dict[str, list[str]] = {
        "weather": ["Buscando clima…"],
        "air": ["Calidad del aire no disponible."],
        "pollen": ["Polen no disponible."],
    }
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {
            pool.submit(_safe_web_lines, query, fallback, kind=kind): key
            for key, (query, fallback, kind) in tasks.items()
        }
        for future in as_completed(futures, timeout=22):
            key = futures[future]
            try:
                results[key] = future.result()
            except Exception:  # noqa: BLE001
                logger.warning("[LIFE] web section timeout key=%s", key)
    return results["weather"], results["air"], results["pollen"]


def _weather_cache_key(user_id: str) -> str:
    return (user_id or "").strip() or "__anon__"


def is_weather_cache_expired(user_id: str) -> bool:
    entry = _WEATHER_CACHE.get(_weather_cache_key(user_id))
    if not entry:
        return True
    expires_at = entry.get("expires_at")
    if not isinstance(expires_at, datetime):
        return True
    return datetime.now(timezone.utc) >= expires_at


def update_weather_cache(user_id: str) -> None:
    """Actualiza clima/aire/polen en background sin bloquear endpoints."""
    from app.modules.environment_module import resolve_environment_place

    place = resolve_environment_place(user_id, "") or _DEFAULT_PLACE
    weather_lines, air_lines, pollen_lines = _fetch_web_sections(place)
    _WEATHER_CACHE[_weather_cache_key(user_id)] = {
        "place": place,
        "weather_lines": weather_lines,
        "air_lines": air_lines,
        "pollen_lines": pollen_lines,
        "updated_at": datetime.now(timezone.utc),
        "expires_at": datetime.now(timezone.utc) + _WEATHER_CACHE_TTL,
    }


def _weather_snapshot(user_id: str) -> tuple[str, list[str], list[str], list[str], bool]:
    entry = _WEATHER_CACHE.get(_weather_cache_key(user_id))
    if not entry:
        return (
            _DEFAULT_PLACE,
            ["Cargando clima…"],
            ["Calidad del aire cargando…"],
            ["Polen cargando…"],
            True,
        )
    return (
        str(entry.get("place") or _DEFAULT_PLACE),
        list(entry.get("weather_lines") or ["Cargando clima…"]),
        list(entry.get("air_lines") or ["Calidad del aire cargando…"]),
        list(entry.get("pollen_lines") or ["Polen cargando…"]),
        False,
    )


def build_life_dashboard(user_id: str) -> dict[str, Any]:
    """Snapshot LIFE inmediato — clima desde cache (sin bloquear event loop)."""
    place, weather_lines, air_lines, pollen_lines, weather_loading = _weather_snapshot(user_id)

    payload = {
        "date_label": _date_label(),
        "place": place,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "weather": {"title": "CLIMA", "lines": weather_lines},
        "air_quality": {"title": "CALIDAD DEL AIRE", "lines": air_lines},
        "pollen": {"title": "POLEN", "lines": pollen_lines},
    }
    if weather_loading:
        payload["weather_loading"] = True
    return payload


def build_life_dashboard_fallback(user_id: str = "") -> dict[str, Any]:
    """Respuesta mínima útil cuando el handler falla por completo."""
    _ = user_id
    return {
        "date_label": _date_label(),
        "place": _DEFAULT_PLACE,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "partial": True,
        "weather": {"title": "CLIMA", "lines": ["Buscando clima…"]},
        "air_quality": {"title": "CALIDAD DEL AIRE", "lines": ["No disponible."]},
        "pollen": {"title": "POLEN", "lines": ["No disponible."]},
    }
