"""Snapshot agregado del carrusel HUD (7 tarjetas)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services.hud_business import fetch_business_card
from app.services.hud_health import build_detailed_health, health_card_lines
from app.services.hud_instagram import fetch_instagram_card
from app.services.hud_leads import fetch_leads_card
from app.services.hud_news import fetch_hud_news_lines
from app.services.hud_trending import fetch_trending_card
from app.services.supabase_db import get_profile, list_activity_lines


def build_carousel_snapshot(user_id: str) -> dict[str, Any]:
    profile = get_profile(user_id) or {}
    prospection_mode = bool(profile.get("prospection_enabled"))
    news = fetch_hud_news_lines()
    health = build_detailed_health()
    activity_lines = list_activity_lines(user_id, limit=3)
    instagram = fetch_instagram_card(user_id)
    leads = fetch_leads_card(user_id)
    trending = fetch_trending_card(user_id)
    business = fetch_business_card(user_id)
    system_accent = "green" if health.get("ok") else "red"

    cards: list[dict[str, Any]] = [
        {
            "id": "news",
            "kind": "news",
            "title": "NEWS",
            "accent": "cyan",
            "badge": "📰",
            "lines": news["lines"],
            "footer": news.get("footer"),
        },
        {
            "id": "instagram",
            "kind": "instagram",
            "title": "INSTAGRAM",
            "accent": "pink",
            "badge": "📷",
            "lines": instagram["lines"],
            "footer": instagram.get("footer"),
        },
        {
            "id": "leads",
            "kind": "leads",
            "title": "LEADS HOY",
            "accent": "red" if prospection_mode else leads.get("accent", "red"),
            "badge": "🎯",
            "lines": leads["lines"],
            "footer": leads.get("footer"),
            "emphasis": prospection_mode,
        },
        {
            "id": "trending",
            "kind": "trending",
            "title": "TRENDING",
            "accent": "orange",
            "badge": "🔥",
            "lines": trending["lines"],
            "footer": trending.get("footer"),
        },
        {
            "id": "activity",
            "kind": "activity",
            "title": "ACTIVIDAD CED",
            "accent": "cyan",
            "badge": "📊",
            "lines": activity_lines
            or [
                "Sin actividad reciente",
                "Habla con CED para ver historial",
            ],
        },
        {
            "id": "business",
            "kind": "business",
            "title": "TU NEGOCIO",
            "accent": "gold",
            "badge": "📈",
            "lines": business["lines"],
            "footer": business.get("footer"),
        },
        {
            "id": "system",
            "kind": "system",
            "title": "SYSTEM",
            "accent": system_accent,
            "badge": "⚡",
            "lines": health_card_lines(health),
            "footer": health.get("checked_at", "")[:19].replace("T", " UTC · "),
        },
    ]

    if prospection_mode:
        # En modo prospección, tarjeta LEADS primero (después de news).
        lead_card = next(c for c in cards if c["id"] == "leads")
        cards = [cards[0], lead_card] + [c for c in cards[1:] if c["id"] != "leads"]

    return {
        "cards": cards,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "health": health,
        "prospection_mode": prospection_mode,
    }
