"""Leads del día para carrusel HUD."""

from __future__ import annotations

from typing import Any

from app.services import supabase_db


def fetch_leads_card(user_id: str) -> dict[str, Any]:
    leads = supabase_db.list_leads_today(user_id, limit=3)
    count = len(leads)

    if not leads:
        return {
            "lines": ["0 leads hoy", "Activa prospección o importa leads"],
            "footer": "detected_leads",
            "accent": "red",
        }

    hot = [l for l in leads if l.get("is_hot")]
    accent = "red" if hot else "orange"
    top = leads[0]
    handle = str(top.get("handle") or "@lead")
    score = int(top.get("score") or 0)
    hot_tag = " · HOT" if top.get("is_hot") else ""

    lines = [
        f"{count} lead{'s' if count != 1 else ''} hoy",
        f"{handle} · score {score}{hot_tag}",
    ]
    if len(leads) > 1:
        second = leads[1]
        lines.append(
            f"{second.get('handle')} · {second.get('score')}"
            + (" HOT" if second.get("is_hot") else "")
        )

    return {
        "lines": lines[:3],
        "footer": "Tiempo real · Supabase",
        "accent": accent,
    }
