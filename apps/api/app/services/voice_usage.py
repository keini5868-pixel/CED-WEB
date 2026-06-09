"""Estado de cupo Gemini Live — compartido por usage y admin."""

from __future__ import annotations

from app.domain.plans import USAGE_WARNING_PERCENT, normalize_plan_id, recharge_balance_to_bonus_minutes
from app.services import supabase_db
from app.services.admin_users import get_user_access

ACCESS_DENIED_MESSAGES = {
    "trial_expired": "Tu prueba de 7 días terminó. Elige un plan para seguir con voz y chat.",
    "Sin suscripción activa": "No tienes suscripción activa. Elige un plan en Precios.",
    "Suscripción inactiva": "Tu suscripción no está activa. Renueva en Precios o contacta soporte.",
    "Cuenta pausada por administrador": "Tu cuenta está pausada. Contacta al administrador.",
}


def voice_access_state(user_id: str) -> dict:
    """Estado unificado de cupo voz — usado por balance, start y tick."""
    try:
        used = supabase_db.get_usage_minutes_today(user_id)
    except RuntimeError:
        used = 0.0

    allowed, access_msg, plan_minutes = get_user_access(user_id)
    sub = supabase_db.get_subscription(user_id)
    plan_id = normalize_plan_id((sub or {}).get("plan_id"))
    try:
        recharge_balance = supabase_db.get_recharge_balance_usd(user_id)
    except RuntimeError:
        recharge_balance = 0.0
    bonus_minutes = recharge_balance_to_bonus_minutes(recharge_balance)
    total_available = (plan_minutes + bonus_minutes) if allowed else 0.0

    access_denied = not allowed and access_msg not in ("free_basic", "trial")
    quota_exhausted = allowed and total_available > 0 and used >= total_available

    if access_denied:
        voice_blocked = False
    elif not allowed and access_msg == "free_basic":
        voice_blocked = plan_minutes <= 0 and bonus_minutes <= 0
    elif allowed and total_available <= 0:
        voice_blocked = True
    else:
        voice_blocked = quota_exhausted

    pct = (used / plan_minutes * 100) if plan_minutes else 0

    return {
        "plan_id": plan_id,
        "subscription_status": (sub or {}).get("status"),
        "trial_ends_at": (sub or {}).get("trial_ends_at"),
        "is_founding_member": bool((sub or {}).get("price_locked_for_life")),
        "price_locked_for_life": bool((sub or {}).get("price_locked_for_life")),
        "plan_minutes_daily": plan_minutes,
        "used_minutes_today": round(used, 2),
        "recharge_balance_usd": round(recharge_balance, 2),
        "bonus_minutes_from_balance": bonus_minutes,
        "total_available_minutes": round(total_available, 2),
        "warning_at_percent": USAGE_WARNING_PERCENT,
        "blocked": voice_blocked,
        "quota_exhausted": quota_exhausted,
        "needs_recharge": quota_exhausted and allowed and recharge_balance <= 0 and plan_minutes > 0,
        "access_denied": access_denied,
        "access_message": access_msg if (not allowed or access_msg in ("free_basic", "trial")) else None,
        "usage_percent": round(pct, 1),
        "timezone": "America/Mexico_City",
        "allowed": allowed,
        "has_stripe_customer": bool((sub or {}).get("stripe_customer_id")),
    }
