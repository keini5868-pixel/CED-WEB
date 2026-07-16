"""Estado de cupo Gemini Live — compartido por usage y admin."""

from __future__ import annotations

import logging

from app.domain.plans import USAGE_WARNING_PERCENT, normalize_plan_id, recharge_balance_to_bonus_minutes
from app.services.async_sync import run_sync
from app.services import supabase_db
from app.services.admin_users import get_user_access

logger = logging.getLogger(__name__)

ACCESS_DENIED_MESSAGES = {
    "trial_expired": (
        "Tu prueba de 7 días de voz terminó. Adquiere un plan o recarga desde $10. "
        "El chat de texto sigue disponible en plan Básico gratis."
    ),
    "Sin suscripción activa": "No tienes suscripción activa. Elige un plan en Precios.",
    "Suscripción inactiva": "Tu suscripción no está activa. Renueva en Precios o contacta soporte.",
    "Cuenta pausada por administrador": "Tu cuenta está pausada. Contacta al administrador.",
}


def degraded_voice_access_state(*, reason: str = "telemetry_unavailable") -> dict:
    """Estado seguro cuando Supabase/telemetría falla — nunca bloquear voz por esto."""
    return {
        "plan_id": None,
        "subscription_status": None,
        "trial_ends_at": None,
        "is_founding_member": False,
        "price_locked_for_life": False,
        "plan_minutes_daily": 0,
        "used_minutes_today": 0.0,
        "recharge_balance_usd": 0.0,
        "bonus_minutes_from_balance": 0.0,
        "total_available_minutes": 0.0,
        "warning_at_percent": USAGE_WARNING_PERCENT,
        "blocked": False,
        "quota_exhausted": False,
        "needs_recharge": False,
        "access_denied": False,
        "access_message": None,
        "usage_percent": 0.0,
        "timezone": "America/Mexico_City",
        "allowed": True,
        "has_stripe_customer": False,
        "degraded": True,
        "degraded_reason": (reason or "telemetry_unavailable")[:240],
    }


def voice_access_state(user_id: str) -> dict:
    """Estado unificado de cupo voz — usado por balance, start y tick."""
    try:
        try:
            used = supabase_db.get_usage_minutes_today(user_id)
        except Exception as exc:  # noqa: BLE001 — best-effort telemetría
            logger.warning(
                "[USAGE] get_usage_minutes_today fallo user=%s: %s",
                user_id[:8],
                exc,
            )
            used = 0.0

        allowed, access_msg, plan_minutes = get_user_access(user_id)
        sub = supabase_db.get_subscription(user_id)
        plan_id = normalize_plan_id((sub or {}).get("plan_id"))
        try:
            recharge_balance = supabase_db.get_recharge_balance_usd(user_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[USAGE] get_recharge_balance_usd fallo user=%s: %s",
                user_id[:8],
                exc,
            )
            recharge_balance = 0.0
        bonus_minutes = recharge_balance_to_bonus_minutes(recharge_balance)
        # free_basic / sin plan: monedero puede desbloquear voz
        free_basic = (not allowed and access_msg == "free_basic") or plan_id == "free_basic"
        wallet_unlocks = bonus_minutes > 0
        effective_allowed = allowed or (free_basic and wallet_unlocks)
        total_available = (
            (plan_minutes + bonus_minutes) if effective_allowed else 0.0
        )

        access_denied = not allowed and access_msg not in ("free_basic", "trial")
        quota_exhausted = (
            effective_allowed and total_available > 0 and used >= total_available
        )

        if access_denied:
            voice_blocked = False
        elif free_basic and not wallet_unlocks and plan_minutes <= 0:
            voice_blocked = True
        elif effective_allowed and total_available <= 0:
            voice_blocked = True
        else:
            voice_blocked = quota_exhausted

        needs_recharge = bool(voice_blocked) and not access_denied
        pct = (used / plan_minutes * 100) if plan_minutes else (
            100.0 if voice_blocked and used > 0 else 0.0
        )

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
            "needs_recharge": needs_recharge,
            "access_denied": access_denied,
            "access_message": access_msg
            if (not allowed or access_msg in ("free_basic", "trial"))
            else None,
            "usage_percent": round(pct, 1),
            "timezone": "America/Mexico_City",
            "allowed": effective_allowed,
            "has_stripe_customer": bool((sub or {}).get("stripe_customer_id")),
            "degraded": False,
        }
    except Exception as exc:  # noqa: BLE001 — nunca 500 por telemetría
        logger.warning(
            "[USAGE] voice_access_state degraded user=%s: %s",
            user_id[:8],
            exc,
        )
        return degraded_voice_access_state(reason=str(exc))


async def voice_access_state_async(user_id: str) -> dict:
    """Misma lógica que voice_access_state, sin bloquear el event loop."""
    return await run_sync(voice_access_state, user_id)
