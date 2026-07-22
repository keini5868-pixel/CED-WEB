"""Catálogo de oportunidades — solo plugins available (sin coming_soon en v1)."""

from __future__ import annotations

from typing import Any, Callable

from app.services.opportunities_pilot.plugins.fitline_pm import (
    OPPORTUNITY_ID,
    fitline_pm_plugin,
)

_PLUGINS: dict[str, Callable[[], dict[str, Any]]] = {
    OPPORTUNITY_ID: fitline_pm_plugin,
}


def list_plugins() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for factory in _PLUGINS.values():
        plugin = factory()
        if plugin.get("status") != "available":
            continue
        out.append(plugin)
    return out


def get_plugin(opportunity_id: str) -> dict[str, Any] | None:
    factory = _PLUGINS.get((opportunity_id or "").strip())
    if not factory:
        return None
    plugin = factory()
    if plugin.get("status") != "available":
        return None
    return plugin


def catalog_summaries() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for plugin in list_plugins():
        rows.append(
            {
                "id": str(plugin["id"]),
                "title": str(plugin.get("title") or ""),
                "tagline": str(plugin.get("tagline") or ""),
                "status": "available",
            }
        )
    return rows
