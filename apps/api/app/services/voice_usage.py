"""Estado de cupo Gemini Live — compartido por usage y admin."""

from __future__ import annotations

import logging

from app.domain.plans import (
    USAGE_WARNING_PERCENT,
    normalize_plan_id,
    plan_uses_gemini_voice_stack,
    plan_voice_transport,
    recharge_balance_to_bonus_minutes,
)
from app.services.async_sync import run_sync
from app.services import supabase_db
from app.services.admin_users import get_user_access

logger = logging.getLogger(__name__)

ACCESS_DENIED_MESSAGES = {
    "trial_expired": (
        "Tu prueba de 7 días terminó. Adquiere un plan o recarga "
        "desde $10. El chat de texto sigue disponible en plan Básico gratis."
    ),
    "voice_trial_expired": (
        "Tu tiempo de prueba de voz (15 minutos desde el registro) se agotó. "
        "Adquiere un plan o recarga desde $10. Imágenes, PDF y chat siguen "
        "disponibles mientras dure tu prueba de 7 días."
    ),
    "cierre_trial_expired": (
        "Tu prueba FitLine de 7 días terminó. Suscríbete a CED PM International "
        "($22/mes) o recarga desde $10. El chat de texto sigue disponible."
    ),
    "past_due": (
        "Hay un pago pendiente en tu suscripción. Las funciones de plan están "
        "pausadas hasta que se resuelva el cobro. Puedes recargar saldo o actualizar "
        "el método de pago en Planes."
    ),
    "Sin suscripción activa": "No tienes suscripción activa. Elige un plan en Planes.",
    "Suscripción inactiva": "Tu suscripción no está activa. Renueva en Planes o contacta soporte.",
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
        "voice_stack": "retell",
        "voice_transport": "retell",
        "voice_pool_trial": False,
    }


def staff_auth_kwargs(user: dict | None) -> dict[str, str | None]:
    """Email/rol del JWT para cupo staff aunque el perfil en DB falle."""
    if not user:
        return {"email": None, "role": None}
    email = user.get("email")
    role = user.get("role")
    return {
        "email": email if isinstance(email, str) else None,
        "role": role if isinstance(role, str) else None,
    }


def voice_access_state(
    user_id: str,
    *,
    email: str | None = None,
    role: str | None = None,
) -> dict:
    """Estado unificado de cupo voz — usado por balance, start y tick."""
    try:
        from app.deps.auth import is_staff_admin

        profile_early = supabase_db.get_profile(user_id) or {}
        staff_email = (email or "").strip() or profile_early.get("email")
        staff_role = role if isinstance(role, str) else (
            profile_early.get("role") if isinstance(profile_early.get("role"), str) else None
        )
        if is_staff_admin(staff_email, staff_role):
            sub = supabase_db.get_subscription(user_id)
            plan_id = normalize_plan_id((sub or {}).get("plan_id"))
            return {
                "plan_id": plan_id,
                "subscription_status": (sub or {}).get("status"),
                "trial_ends_at": (sub or {}).get("trial_ends_at"),
                "is_founding_member": bool((sub or {}).get("price_locked_for_life")),
                "price_locked_for_life": bool((sub or {}).get("price_locked_for_life")),
                "plan_minutes_daily": 99_999,
                "used_minutes_today": 0.0,
                "recharge_balance_usd": 0.0,
                "bonus_minutes_from_balance": 0.0,
                "total_available_minutes": 99_999.0,
                "warning_at_percent": USAGE_WARNING_PERCENT,
                "blocked": False,
                "quota_exhausted": False,
                "needs_recharge": False,
                "access_denied": False,
                "access_message": None,
                "usage_percent": 0.0,
                "timezone": "America/Mexico_City",
                "allowed": True,
                "has_stripe_customer": bool((sub or {}).get("stripe_customer_id")),
                "degraded": False,
                "voice_stack": "retell",
                "voice_transport": "retell",
                "preview_as": None,
                "staff_unlimited": True,
                "voice_pool_trial": False,
            }

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

        # Trial: pool único de 15 min desde el registro. No se renueva a
        # medianoche ni a las 24 h. Comparar uso acumulado desde created_at.
        from app.domain.plans import is_voice_pool_trial

        if allowed and access_msg in (
            "cierre_trial",
            "trial",
            "voice_trial_expired",
        ) and is_voice_pool_trial(sub):
            try:
                used = supabase_db.get_cierre_trial_used_minutes(user_id, sub)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "[USAGE] get_cierre_trial_used_minutes fallo user=%s: %s",
                    user_id[:8],
                    exc,
                )
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
        # free_basic / past_due / voz de trial agotada: sin minutos de plan;
        # monedero puede desbloquear voz.
        restricted_plan = access_msg in (
            "free_basic",
            "past_due",
            "voice_trial_expired",
            "trial_expired",
            "cierre_trial_expired",
        ) or plan_id == "free_basic"
        wallet_unlocks = bonus_minutes > 0

        # Trial calendario vencido: el monedero SÍ debe abrir voz (antes se bloqueaba).
        if not allowed and access_msg in ("trial_expired", "cierre_trial_expired"):
            if wallet_unlocks:
                effective_allowed = True
                total_available = bonus_minutes
            else:
                effective_allowed = False
                total_available = 0.0
        elif restricted_plan:
            effective_allowed = wallet_unlocks
            total_available = bonus_minutes if wallet_unlocks else 0.0
        elif allowed and access_msg in ("ok", "trial", "cierre_trial"):
            effective_allowed = True
            total_available = float(plan_minutes) + bonus_minutes
        else:
            effective_allowed = False
            total_available = 0.0

        access_denied = not allowed and access_msg not in (
            "free_basic",
            "trial",
            "cierre_trial",
            "voice_trial_expired",
            "past_due",
            "trial_expired",
            "cierre_trial_expired",
        )
        quota_exhausted = (
            effective_allowed and total_available > 0 and used >= total_available
        )

        if access_denied:
            voice_blocked = True
        elif (
            not allowed
            and access_msg in ("trial_expired", "cierre_trial_expired")
            and not wallet_unlocks
        ):
            voice_blocked = True
        elif restricted_plan and not wallet_unlocks:
            voice_blocked = True
        elif effective_allowed and total_available <= 0:
            voice_blocked = True
        else:
            voice_blocked = quota_exhausted

        # Con trial vencido y sin monedero, sí mostrar “necesita recarga”.
        needs_recharge = bool(voice_blocked)
        pct = (
            (used / total_available * 100) if total_available else (
                100.0 if voice_blocked and used > 0 else 0.0
            )
        )

        # Preview admin → socio Cierre: stack OpenAI (sin Retell/Jarvis).
        preview_as = ""
        effective_plan = plan_id
        try:
            from app.services.preview_persona import (
                effective_plan_id_for_voice,
                get_preview_as,
                is_cierre_partner_preview,
            )

            if is_cierre_partner_preview(user_id):
                preview_as = get_preview_as()
                effective_plan = effective_plan_id_for_voice(user_id, plan_id)
        except Exception:  # noqa: BLE001
            pass

        return {
            "plan_id": effective_plan if preview_as else plan_id,
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
            if (
                not allowed
                or access_msg
                in (
                    "free_basic",
                    "trial",
                    "cierre_trial",
                    "cierre_trial_expired",
                    "trial_expired",
                    "voice_trial_expired",
                    "past_due",
                )
            )
            else None,
            "usage_percent": round(pct, 1),
            "timezone": "America/Mexico_City",
            "allowed": effective_allowed,
            "has_stripe_customer": bool((sub or {}).get("stripe_customer_id")),
            "degraded": False,
            "voice_stack": (
                "gemini" if plan_uses_gemini_voice_stack(effective_plan) else "retell"
            ),
            "voice_transport": plan_voice_transport(effective_plan),
            "preview_as": preview_as or None,
            "voice_pool_trial": bool(
                allowed
                and access_msg
                in ("cierre_trial", "trial", "voice_trial_expired")
                and is_voice_pool_trial(sub)
            ),
            "voice_trial_started_at": (sub or {}).get("voice_trial_started_at"),
        }
    except Exception as exc:  # noqa: BLE001 — nunca 500 por telemetría
        logger.warning(
            "[USAGE] voice_access_state degraded user=%s: %s",
            user_id[:8],
            exc,
        )
        return degraded_voice_access_state(reason=str(exc))


async def voice_access_state_async(
    user_id: str,
    *,
    email: str | None = None,
    role: str | None = None,
) -> dict:
    """Misma lógica que voice_access_state, sin bloquear el event loop."""
    return await run_sync(voice_access_state, user_id, email=email, role=role)
