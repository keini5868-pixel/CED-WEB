"""HUD Life dashboard — clima, calendario, gmail, aire y polen."""

from __future__ import annotations

import logging
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


def _date_label() -> str:
    now = datetime.now(_TZ)
    day = _DAYS_ES[now.weekday()]
    month = _MONTHS_ES[now.month - 1]
    return f"{day} {now.day} de {month}, {now.year}"


def _web_lines(query: str, *, kind: str = "weather") -> list[str]:
    from app.services.gemini_grounded import execute_search_web_sync

    result = execute_search_web_sync(query, kind=kind)
    summary = str(result.get("summary") or result.get("message") or "").strip()
    if not summary:
        return []
    parts = [p.strip() for p in summary.replace("·", ".").split(".") if p.strip()]
    if parts:
        return parts[:4]
    return [summary[:240]]


def _safe_web_lines(query: str, fallback: str, *, kind: str = "weather") -> list[str]:
    try:
        lines = _web_lines(query, kind=kind)
        if lines:
            return lines
    except Exception:  # noqa: BLE001
        logger.warning("[LIFE] web search failed query=%s", query[:80], exc_info=True)
    return [fallback]


def _calendar_section(user_id: str) -> dict[str, Any]:
    section: dict[str, Any] = {
        "connected": False,
        "events": [],
        "hint": "Conectar Calendar en CFG ⚙️",
    }
    try:
        from app.services.google_calendar_api import list_events, resolve_window
        from app.services.google_oauth import get_valid_access_token

        token = get_valid_access_token("calendar", user_id)
        start, end = resolve_window("today")
        events = list_events(token, time_min=start, time_max=end, max_results=6)
        section["connected"] = True
        section["events"] = events or ["Sin eventos programados para hoy."]
        section["hint"] = ""
    except ValueError:
        pass
    except Exception:  # noqa: BLE001
        logger.warning("[LIFE] calendar load failed user=%s", user_id[:8], exc_info=True)
        section["hint"] = "Conectar Calendar en CFG ⚙️"
    return section


def _gmail_section(user_id: str) -> dict[str, Any]:
    section: dict[str, Any] = {
        "connected": False,
        "unread_count": 0,
        "messages": [],
        "hint": "Conectar Gmail en CFG ⚙️",
    }
    try:
        from app.services.google_gmail_api import list_messages
        from app.services.google_oauth import get_valid_access_token

        token = get_valid_access_token("gmail", user_id)
        msgs = list_messages(token, query="is:unread", max_results=5)
        section["connected"] = True
        section["unread_count"] = len(msgs)
        section["messages"] = [
            f"{m.get('from', '?')} — {m.get('subject', '(sin asunto)')}" for m in msgs[:3]
        ]
        section["hint"] = ""
        if not msgs:
            section["messages"] = ["Bandeja al día — sin correos sin leer."]
    except ValueError:
        pass
    except Exception:  # noqa: BLE001
        logger.warning("[LIFE] gmail load failed user=%s", user_id[:8], exc_info=True)
        section["hint"] = "Conectar Gmail en CFG ⚙️"
    return section


def _fetch_web_sections(place: str) -> tuple[list[str], list[str], list[str]]:
    tasks = {
        "weather": (
            f"clima {place} hoy temperatura humedad viento",
            "Clima no disponible.",
        ),
        "air": (
            f"calidad del aire {place} hoy índice",
            "Calidad del aire no disponible.",
        ),
        "pollen": (
            f"polen {place} hoy niveles árbol pasto",
            "Polen no disponible.",
        ),
    }
    results: dict[str, list[str]] = {
        "weather": ["Buscando clima…"],
        "air": ["Calidad del aire no disponible."],
        "pollen": ["Polen no disponible."],
    }
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {
            pool.submit(_safe_web_lines, query, fallback, kind="weather"): key
            for key, (query, fallback) in tasks.items()
        }
        for future in as_completed(futures, timeout=22):
            key = futures[future]
            try:
                results[key] = future.result()
            except Exception:  # noqa: BLE001
                logger.warning("[LIFE] web section timeout key=%s", key)
    return results["weather"], results["air"], results["pollen"]


def build_life_dashboard(user_id: str) -> dict[str, Any]:
    """Snapshot LIFE — cada sección tolera fallos parciales."""
    from app.modules.environment_module import resolve_environment_place

    place = resolve_environment_place(user_id, "") or _DEFAULT_PLACE

    try:
        weather_lines, air_lines, pollen_lines = _fetch_web_sections(place)
    except Exception:  # noqa: BLE001
        logger.warning("[LIFE] web sections failed user=%s", user_id[:8], exc_info=True)
        weather_lines = ["Clima no disponible."]
        air_lines = ["Calidad del aire no disponible."]
        pollen_lines = ["Polen no disponible."]

    calendar = _calendar_section(user_id)
    gmail = _gmail_section(user_id)

    return {
        "date_label": _date_label(),
        "place": place,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "weather": {"title": "CLIMA", "lines": weather_lines},
        "calendar": {"title": "CALENDARIO", **calendar},
        "gmail": {"title": "GMAIL", **gmail},
        "air_quality": {"title": "CALIDAD DEL AIRE", "lines": air_lines},
        "pollen": {"title": "POLEN", "lines": pollen_lines},
    }


def build_life_dashboard_fallback(user_id: str = "") -> dict[str, Any]:
    """Respuesta mínima útil cuando el handler falla por completo."""
    calendar = _calendar_section(user_id) if user_id else {
        "connected": False,
        "events": [],
        "hint": "Conectar Calendar en CFG ⚙️",
    }
    gmail = _gmail_section(user_id) if user_id else {
        "connected": False,
        "unread_count": 0,
        "messages": [],
        "hint": "Conectar Gmail en CFG ⚙️",
    }
    return {
        "date_label": _date_label(),
        "place": _DEFAULT_PLACE,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "partial": True,
        "weather": {"title": "CLIMA", "lines": ["Buscando clima…"]},
        "calendar": {"title": "CALENDARIO", **calendar},
        "gmail": {"title": "GMAIL", **gmail},
        "air_quality": {"title": "CALIDAD DEL AIRE", "lines": ["No disponible."]},
        "pollen": {"title": "POLEN", "lines": ["No disponible."]},
    }
