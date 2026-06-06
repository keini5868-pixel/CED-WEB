"""Clasifica resultados de búsqueda en paneles HUD."""

from __future__ import annotations

from typing import Any

HudPanelId = str


def classify_panel(title: str, snippet: str) -> HudPanelId:
    blob = f"{title} {snippet}".lower()
    if any(k in blob for k in ("noticia", "news", "anuncia", "reporta", "según")):
        return "drones"
    if any(
        k in blob
        for k in (
            "%",
            "millones",
            "crecimiento",
            "estadística",
            "kpi",
            "usuarios",
            "ventas",
            "precio",
        )
    ):
        return "waves"
    if any(k in blob for k in ("global", "mercado", "industria", "economía", "país")):
        return "global"
    return "drones"


def panel_payload(title: str, snippet: str, url: str = "") -> dict[str, Any]:
    return {
        "title": title[:120],
        "text": snippet[:220],
        "url": url,
    }
