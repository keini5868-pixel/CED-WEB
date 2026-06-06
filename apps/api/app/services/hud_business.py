"""Métricas de negocio para carrusel HUD."""

from __future__ import annotations

from typing import Any

from app.services import supabase_db


def fetch_business_card(user_id: str) -> dict[str, Any]:
    profile = supabase_db.get_profile(user_id)
    sub = supabase_db.get_subscription(user_id)
    used_week = supabase_db.get_usage_minutes_week(user_id)

    founding = bool((profile or {}).get("is_founding_member"))
    status = (sub or {}).get("status") or ("active" if founding else "trialing")
    plan = (sub or {}).get("plan_id") or ("elite_founding" if founding else "elite_regular")

    lines = [
        f"Plan {plan.replace('_', ' ')} · {status}",
        f"Voz esta semana: {used_week:.0f} min",
    ]

    if founding:
        slot = (profile or {}).get("founding_slot_number")
        if slot:
            lines.append(f"Founding slot #{slot} · precio bloqueado")
        else:
            lines.append("Miembro fundador · precio bloqueado")
    else:
        lines.append("Stripe checkout · Fase 7")

    return {
        "lines": lines[:3],
        "footer": "Tu negocio CED",
    }
