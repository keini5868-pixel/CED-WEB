"""HUD Life dashboard — clima, calendario, gmail, aire y polen."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any

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
        return ["Datos no disponibles en este momento."]
    parts = [p.strip() for p in summary.replace("·", ".").split(".") if p.strip()]
    if parts:
        return parts[:4]
    return [summary[:240]]


def _calendar_section(user_id: str) -> dict[str, Any]:
    section: dict[str, Any] = {
        "connected": False,
        "events": [],
        "hint": "Conecte Google Calendar en CFG de voz para ver eventos.",
    }
    try:
        from app.services.google_calendar_api import list_events, resolve_window
        from app.services.google_oauth import get_valid_access_token

        token = get_valid_access_token("calendar", user_id)
        start, end = resolve_window("today")
        events = list_events(token, time_min=start, time_max=end, max_results=6)
        section["connected"] = True
        section["events"] = events
        section["hint"] = ""
        if not events:
            section["events"] = ["Sin eventos programados para hoy."]
    except ValueError:
        pass
    except Exception:  # noqa: BLE001
        section["hint"] = "No se pudo cargar Google Calendar."
    return section


def _gmail_section(user_id: str) -> dict[str, Any]:
    section: dict[str, Any] = {
        "connected": False,
        "unread_count": 0,
        "messages": [],
        "hint": "Conecte Gmail en CFG de voz para ver correos.",
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
        section["hint"] = "No se pudo cargar Gmail."
    return section


def build_life_dashboard(user_id: str) -> dict[str, Any]:
    """Snapshot LIFE — clima vía web; calendar/gmail vía OAuth."""
    from app.modules.environment_module import resolve_environment_place

    place = resolve_environment_place(user_id, "")
    weather_lines = _web_lines(f"clima {place} hoy temperatura humedad viento", kind="weather")
    air_lines = _web_lines(f"calidad del aire {place} hoy índice", kind="weather")
    pollen_lines = _web_lines(f"polen {place} hoy niveles árbol pasto", kind="weather")

    return {
        "date_label": _date_label(),
        "place": place,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "weather": {
            "title": "CLIMA",
            "lines": weather_lines,
        },
        "calendar": {
            "title": "CALENDARIO",
            **_calendar_section(user_id),
        },
        "gmail": {
            "title": "GMAIL",
            **_gmail_section(user_id),
        },
        "air_quality": {
            "title": "CALIDAD DEL AIRE",
            "lines": air_lines,
        },
        "pollen": {
            "title": "POLEN",
            "lines": pollen_lines,
        },
    }
