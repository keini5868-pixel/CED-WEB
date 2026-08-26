"""Creación y listado de usuarios manuales — solo super admin."""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from app.config import get_settings
from app.domain.plans import (
    PLAN_LABELS,
    PLAN_PRICES_USD,
    PlanId,
    normalize_plan_id,
    plan_minutes_daily,
    recharge_balance_to_bonus_minutes,
)
from app.services import supabase_db
from app.services.email_welcome import send_welcome_email

logger = logging.getLogger(__name__)

ACCESS_TYPES = frozenset({"paid", "beta", "founding_gift", "coadmin"})
MAX_CREATIONS_PER_DAY = 10
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_ADMIN_USERS_CACHE: dict[str, Any] | None = None
_ADMIN_USERS_CACHE_AT: float = 0.0
_ADMIN_USERS_CACHE_TTL_SEC = 15.0


class AdminUserError(ValueError):
    pass


def _client():
    return supabase_db._client()


def count_manual_creations_today(admin_id: str) -> int:
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    result = (
        _client()
        .table("admin_audit_logs")
        .select("id", count="exact")
        .eq("admin_user_id", admin_id)
        .eq("action", "USER_CREATED_MANUALLY")
        .gte("created_at", start.isoformat())
        .execute()
    )
    return int(result.count or 0)


def email_exists(email: str) -> bool:
    normalized = email.strip().lower()
    result = (
        _client()
        .table("profiles")
        .select("id")
        .ilike("email", normalized)
        .limit(1)
        .execute()
    )
    return bool(result.data)


def _parse_expires(duration_days: int | str | None) -> datetime | None:
    if duration_days is None or duration_days == "indefinite":
        return None
    days = int(duration_days)
    if days <= 0:
        return None
    return datetime.now(timezone.utc) + timedelta(days=days)


def _subscription_status(access_type: str, expires_at: datetime | None) -> str:
    if access_type in ("beta", "founding_gift"):
        return "active"
    if expires_at and expires_at <= datetime.now(timezone.utc):
        return "expired"
    return "active"


def create_manual_user(
    *,
    admin_id: str,
    name: str,
    email: str,
    phone: str | None,
    access_type: str,
    plan: str,
    duration_days: int | str | None,
    minutes_daily: int,
    initial_balance: float,
    password: str,
    send_welcome_email_flag: bool,
    force_password_change: bool,
    admin_notes: str | None,
    ip_address: str | None,
    user_agent: str | None,
) -> dict[str, Any]:
    if count_manual_creations_today(admin_id) >= MAX_CREATIONS_PER_DAY:
        raise AdminUserError("Límite diario alcanzado (10 usuarios por admin).")

    name = name.strip()
    email = email.strip().lower()
    if not name:
        raise AdminUserError("Nombre requerido.")
    if not EMAIL_RE.match(email):
        raise AdminUserError("Email inválido.")
    if len(password) < 8:
        raise AdminUserError("Contraseña mínimo 8 caracteres.")
    if access_type not in ACCESS_TYPES:
        raise AdminUserError("Tipo de acceso inválido.")
    valid_plans = {
        PlanId.CIERRE.value,
        PlanId.STARTER.value,
        PlanId.PRO.value,
        PlanId.ELITE.value,
        PlanId.FOUNDING.value,
        PlanId.ELITE_FOUNDING.value,
        PlanId.ELITE_REGULAR.value,
    }
    if plan not in valid_plans:
        raise AdminUserError("Plan inválido.")
    plan = normalize_plan_id(plan)
    if minutes_daily < 0 or minutes_daily > 9999:
        raise AdminUserError("Minutos diarios entre 0 y 9999.")
    if initial_balance < 0:
        raise AdminUserError("Saldo inicial no puede ser negativo.")
    if email_exists(email):
        raise AdminUserError("Ya existe un usuario con ese email.")

    expires_at = _parse_expires(duration_days)
    status = _subscription_status(access_type, expires_at)
    is_founding = plan == PlanId.FOUNDING.value
    profile_role = "coadmin" if access_type == "coadmin" else "client"

    client = _client()
    try:
        auth_res = client.auth.admin.create_user(
            {
                "email": email,
                "password": password,
                "email_confirm": True,
                "user_metadata": {
                    "full_name": name,
                    "phone": phone or "",
                    "access_type": access_type,
                    "created_manually": True,
                    "created_by": admin_id,
                    "force_password_change": force_password_change,
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        if "already" in msg.lower() or "duplicate" in msg.lower():
            raise AdminUserError("Email ya registrado en Auth.") from exc
        logger.exception("[ADMIN] create_user auth failed")
        raise AdminUserError(f"No se pudo crear en Auth: {msg}") from exc

    user = auth_res.user if hasattr(auth_res, "user") else (auth_res or {}).get("user")
    user_id = str(getattr(user, "id", None) or (user or {}).get("id") or "")
    if not user_id:
        raise AdminUserError("Auth no devolvió user_id.")

    now = datetime.now(timezone.utc).isoformat()
    period_end = expires_at.isoformat() if expires_at else None

    try:
        client.table("profiles").update(
            {
                "full_name": name,
                "phone": phone,
                "role": profile_role,
                "is_founding_member": is_founding,
                "price_locked_usd": PLAN_PRICES_USD.get(plan, 99),
                "admin_notes": admin_notes,
                "updated_at": now,
            }
        ).eq("id", user_id).execute()

        client.table("subscriptions").upsert(
            {
                "user_id": user_id,
                "plan_id": plan,
                "access_type": access_type,
                "status": status,
                "stripe_customer_id": None,
                "stripe_subscription_id": None,
                "created_by": admin_id,
                "expires_at": period_end,
                "current_period_end": period_end,
                "price_locked_for_life": is_founding and access_type != "beta",
                "admin_notes": admin_notes,
                "updated_at": now,
            },
            on_conflict="user_id",
        ).execute()

        client.table("usage_limits").upsert(
            {
                "user_id": user_id,
                "minutes_daily": minutes_daily,
                "updated_at": now,
            },
            on_conflict="user_id",
        ).execute()

        client.table("recharge_balances").upsert(
            {"user_id": user_id, "balance_usd": round(initial_balance, 2), "updated_at": now},
            on_conflict="user_id",
        ).execute()

        if initial_balance > 0:
            client.table("transactions").insert(
                {
                    "user_id": user_id,
                    "type": "admin_grant",
                    "amount_usd": round(initial_balance, 2),
                    "metadata": {
                        "reason": "initial_balance",
                        "admin_id": admin_id,
                    },
                }
            ).execute()
    except Exception as exc:  # noqa: BLE001
        logger.exception("[ADMIN] post-create db failed user=%s", user_id)
        try:
            client.auth.admin.delete_user(user_id)
        except Exception:  # noqa: BLE001
            pass
        raise AdminUserError(f"Error al configurar cuenta: {exc}") from exc

    supabase_db.log_admin_audit(
        admin_id,
        "USER_CREATED_MANUALLY",
        target_user_id=user_id,
        payload={
            "access_type": access_type,
            "plan": plan,
            "duration_days": duration_days,
            "minutes_daily": minutes_daily,
            "initial_balance": initial_balance,
            "email_sent": send_welcome_email_flag,
        },
        ip_address=ip_address,
        user_agent=user_agent,
    )

    settings = get_settings()
    login_url = f"{settings.web_public_url.rstrip('/')}/login"
    email_sent = False
    email_error: str | None = None
    if send_welcome_email_flag:
        email_sent, email_error = send_welcome_email(
            to_email=email,
            name=name,
            password=password,
            plan_label=PLAN_LABELS.get(plan, plan),
            minutes_daily=minutes_daily,
            login_url=login_url,
        )

    return {
        "success": True,
        "user_id": user_id,
        "email": email,
        "login_url": login_url,
        "temporary_password": password,
        "expires_at": period_end,
        "minutes_daily": minutes_daily,
        "initial_balance": round(initial_balance, 2),
        "email_sent": email_sent,
        "email_error": email_error,
    }


def _user_status(sub: dict[str, Any] | None) -> str:
    if not sub:
        return "sin_plan"
    if sub.get("paused_at"):
        return "paused"
    st = str(sub.get("status") or "")
    if st == "trialing":
        trial_end = sub.get("trial_ends_at") or sub.get("expires_at")
        if trial_end:
            try:
                end_dt = datetime.fromisoformat(str(trial_end).replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                if end_dt <= now:
                    return "expired"
                if end_dt <= now + timedelta(days=2):
                    return "expiring"
            except ValueError:
                pass
        return "trial"
    if st in ("expired", "cancelled", "canceled"):
        return "expired" if st == "expired" else "cancelled"
    exp = sub.get("expires_at") or (
        sub.get("trial_ends_at") if st == "trialing" else None
    )
    if exp:
        try:
            exp_dt = datetime.fromisoformat(str(exp).replace("Z", "+00:00"))
            if exp_dt <= datetime.now(timezone.utc):
                return "expired"
            if exp_dt <= datetime.now(timezone.utc) + timedelta(days=7):
                return "expiring"
        except ValueError:
            pass
    if st == "past_due":
        return "past_due"
    if st == "active":
        return "active"
    return st or "active"


def _plan_display(sub: dict[str, Any] | None) -> dict[str, Any]:
    """Etiquetas claras: trial vs plan pagado vs básico — sin mutar datos."""
    from app.domain.plans import (
        is_cierre_fitline_trial,
        trial_voice_minutes_for_subscription,
    )

    if not sub:
        return {
            "plan": None,
            "plan_label": "Sin plan",
            "is_trial": False,
            "is_paid": False,
            "subscription_status": None,
            "trial_ends_at": None,
            "expires_at": None,
            "display_expires_at": None,
            "voice_minutes_daily": 0,
        }

    raw_plan = sub.get("plan_id")
    plan_id = normalize_plan_id(raw_plan)
    st = str(sub.get("status") or "")
    trial_ends = sub.get("trial_ends_at")
    expires_at = sub.get("expires_at")
    stripe_sub = (sub.get("stripe_subscription_id") or "").strip()
    is_trial = st == "trialing"
    base_label = PLAN_LABELS.get(plan_id, plan_id or "—")

    access_raw = str(sub.get("access_type") or "")
    is_paid = (
        bool(stripe_sub) and st in ("active", "past_due")
    ) or (
        access_raw == "paid"
        and st == "active"
        and plan_id not in (PlanId.FREE_BASIC.value, None, "")
    )

    if is_trial:
        if is_cierre_fitline_trial(sub):
            plan_label = "Prueba FitLine · voz 15 min"
        else:
            plan_label = "Prueba de voz · 15 min"
        display_expires = trial_ends or expires_at
        voice_minutes = trial_voice_minutes_for_subscription(sub)
    elif is_paid:
        plan_label = base_label
        display_expires = expires_at
        voice_minutes = plan_minutes_daily(plan_id)
    elif plan_id == PlanId.FREE_BASIC.value:
        plan_label = PLAN_LABELS[PlanId.FREE_BASIC.value]
        display_expires = expires_at
        voice_minutes = 0
    elif st == "active":
        plan_label = base_label
        display_expires = expires_at
        voice_minutes = plan_minutes_daily(plan_id)
    else:
        plan_label = base_label
        display_expires = expires_at or trial_ends
        voice_minutes = 0

    return {
        "plan": plan_id,
        "plan_label": plan_label,
        "is_trial": is_trial,
        "is_paid": is_paid,
        "subscription_status": st or None,
        "trial_ends_at": trial_ends,
        "expires_at": expires_at,
        "display_expires_at": display_expires,
        "voice_minutes_daily": voice_minutes,
    }


def list_admin_users(search: str = "", limit: int = 20) -> dict[str, Any]:
    global _ADMIN_USERS_CACHE, _ADMIN_USERS_CACHE_AT
    safe_limit = min(max(limit, 1), 200)
    cache_key = f"{search.strip().lower()}:{safe_limit}"
    now = time.time()
    if (
        not search.strip()
        and _ADMIN_USERS_CACHE
        and _ADMIN_USERS_CACHE.get("key") == cache_key
        and now - _ADMIN_USERS_CACHE_AT < _ADMIN_USERS_CACHE_TTL_SEC
    ):
        return _ADMIN_USERS_CACHE["data"]

    client = _client()
    query = (
        client.table("profiles")
        .select(
            "id, email, full_name, phone, role, is_founding_member, created_at, "
            "subscriptions!subscriptions_user_id_fkey("
            "plan_id, access_type, status, expires_at, trial_ends_at, paused_at, "
            "stripe_subscription_id"
            "), "
            "usage_limits(minutes_daily)"
        )
        .order("created_at", desc=True)
        .limit(safe_limit)
    )
    if search.strip():
        term = search.strip().replace(",", " ")
        query = query.or_(f"email.ilike.%{term}%,full_name.ilike.%{term}%")

    result = query.execute()
    rows = result.data or []
    ids = [str(r.get("id") or "") for r in rows if r.get("id")]
    wallet_map = supabase_db.get_recharge_balances_map(ids)
    used_today_map = supabase_db.get_usage_minutes_today_map(ids)
    last_recharge_map = supabase_db.get_last_recharges_map(ids)
    users: list[dict[str, Any]] = []
    active = expiring = trial_count = 0

    trial_ids: list[str] = []
    for row in rows:
        subs = row.get("subscriptions") or []
        sub = subs[0] if isinstance(subs, list) and subs else subs if isinstance(subs, dict) else None
        if _plan_display(sub if isinstance(sub, dict) else None).get("is_trial"):
            uid = str(row.get("id") or "")
            if uid:
                trial_ids.append(uid)
    used_trial_map = (
        supabase_db.get_usage_minutes_total_map(trial_ids) if trial_ids else {}
    )

    for row in rows:
        subs = row.get("subscriptions") or []
        sub = subs[0] if isinstance(subs, list) and subs else subs if isinstance(subs, dict) else None
        limits = row.get("usage_limits") or []
        lim = limits[0] if isinstance(limits, list) and limits else limits if isinstance(limits, dict) else None
        status = _user_status(sub)
        plan_info = _plan_display(sub if isinstance(sub, dict) else None)

        if status == "active":
            active += 1
        elif status == "expiring":
            expiring += 1
            active += 1
        elif status == "trial":
            trial_count += 1
            active += 1

        access = (sub or {}).get("access_type") or "paid"
        if row.get("role") == "super_admin":
            access = "admin"
        elif row.get("role") == "coadmin":
            access = "coadmin"
        elif plan_info["is_trial"]:
            access = "trial"
        elif plan_info["plan"] == PlanId.FREE_BASIC.value and not plan_info["is_paid"]:
            access = "free_basic"

        # Minutos: trial = pool de 15 (no diario); si no, usage_limits o cuota del plan.
        if plan_info["is_trial"]:
            minutes = plan_info["voice_minutes_daily"]
        else:
            minutes = (lim or {}).get("minutes_daily") or plan_info["voice_minutes_daily"]

        uid = str(row["id"])
        used = (
            used_trial_map.get(uid, 0.0)
            if plan_info["is_trial"]
            else used_today_map.get(uid, 0.0)
        )
        wallet = wallet_map.get(uid, 0.0)
        bonus = recharge_balance_to_bonus_minutes(wallet)
        has_recharge = wallet > 0.009
        # El saldo de recarga ya baja al usarse: no restar de nuevo el uso.
        plan_left = max(0.0, float(minutes or 0) - used)
        total_available = round(float(minutes or 0) + bonus, 2)
        remaining = round(plan_left + bonus, 2)

        if has_recharge and not plan_info["is_paid"]:
            if plan_info["is_trial"]:
                plan_info = {
                    **plan_info,
                    "plan_label": f"{plan_info['plan_label']} + recarga ${wallet:.2f}",
                }
            else:
                plan_info = {
                    **plan_info,
                    "plan_label": f"Recarga activa · ${wallet:.2f}",
                }
                access = "recharge"

        last = last_recharge_map.get(uid) or {}
        last_paid = float(last.get("amount_paid_usd") or 0)

        users.append(
            {
                "id": row["id"],
                "email": row.get("email"),
                "full_name": row.get("full_name"),
                "phone": row.get("phone"),
                "role": row.get("role"),
                "access_type": access,
                "plan": plan_info["plan"],
                "plan_label": plan_info["plan_label"],
                "is_trial": plan_info["is_trial"],
                "is_paid": plan_info["is_paid"],
                "has_active_recharge": has_recharge,
                "subscription_status": plan_info["subscription_status"],
                "status": status,
                "expires_at": plan_info["display_expires_at"],
                "trial_ends_at": plan_info["trial_ends_at"],
                "period_expires_at": plan_info["expires_at"],
                "minutes_daily": minutes,
                "used_minutes": round(used, 2),
                "recharge_balance_usd": round(wallet, 2),
                "bonus_minutes": bonus,
                "total_available_minutes": total_available,
                "remaining_minutes": remaining,
                "last_recharge_usd": round(last_paid, 2),
                "last_recharge_at": last.get("created_at"),
                "created_at": row.get("created_at"),
                "is_founding_member": row.get("is_founding_member"),
            }
        )

    payload = {
        "users": users,
        "total": len(users),
        "active_count": active,
        "expiring_count": expiring,
        "trial_count": trial_count,
    }
    if not search.strip():
        _ADMIN_USERS_CACHE = {"key": cache_key, "data": payload}
        _ADMIN_USERS_CACHE_AT = now
    return payload


def credit_user_recharge(
    *,
    admin_id: str,
    user_id: str,
    amount_usd: float,
) -> dict[str, Any]:
    """Acredita una recarga (p. ej. Stripe cobró y el webhook no ató al usuario)."""
    global _ADMIN_USERS_CACHE
    from app.domain.plans import quote_recharge, recharge_balance_to_bonus_minutes

    paid = round(float(amount_usd), 2)
    if int(paid) not in (10, 20, 40, 50, 100):
        raise AdminUserError("Monto de recarga no válido (10, 20, 40, 50 o 100).")
    profile = supabase_db.get_profile(user_id)
    if not profile:
        raise AdminUserError("Usuario no encontrado.")
    q = quote_recharge(paid)
    grant_id = f"admin_grant_{user_id[:8]}_{admin_id[:8]}_{int(time.time())}"
    ok = supabase_db.credit_recharge_balance(
        user_id,
        amount_paid_usd=float(q["amount_paid_usd"]),
        client_balance_usd=float(q["client_balance_usd"]),
        margin_keini_usd=float(q["margin_keini_usd"]),
        stripe_event_id=grant_id,
    )
    if not ok:
        raise AdminUserError("No se pudo acreditar la recarga (error de base de datos).")
    try:
        supabase_db.expire_trial_if_needed(user_id)
    except Exception:  # noqa: BLE001
        pass
    supabase_db.log_admin_audit(
        admin_id,
        "RECHARGE_CREDITED_MANUALLY",
        target_user_id=user_id,
        payload={"amount_usd": paid, "client_balance_usd": q["client_balance_usd"]},
    )
    _ADMIN_USERS_CACHE = None
    bal = supabase_db.get_recharge_balance_usd(user_id)
    return {
        "ok": True,
        "user_id": user_id,
        "email": profile.get("email"),
        "amount_paid_usd": paid,
        "client_balance_usd": q["client_balance_usd"],
        "recharge_balance_usd": round(bal, 2),
        "bonus_minutes": recharge_balance_to_bonus_minutes(bal),
    }


def get_user_access(user_id: str) -> tuple[bool, str, int]:
    """Acceso activo + minutos diarios del plan."""
    from app.deps.auth import is_staff_admin
    from app.domain.plans import (
        PlanId,
        get_plan_limits,
        is_cierre_fitline_trial,
        normalize_plan_id,
        plan_minutes_daily,
        trial_voice_minutes_for_subscription,
    )

    profile = supabase_db.get_profile(user_id)
    email = (profile or {}).get("email")
    role = (profile or {}).get("role")
    # Admin / coadmin / super_admin: sin límite práctico de minutos (no corta la llamada).
    if is_staff_admin(email, role if isinstance(role, str) else None):
        return True, "ok", 99_999

    supabase_db.expire_trial_if_needed(user_id)
    sub = supabase_db.get_subscription(user_id)
    if not sub:
        return False, "Sin suscripción activa", 0

    if sub.get("paused_at"):
        return False, "Cuenta pausada por administrador", 0

    plan_id = normalize_plan_id(sub.get("plan_id"))
    limits = get_plan_limits(plan_id)
    st = str(sub.get("status") or "")

    if st == "trialing":
        # expire_trial_if_needed ya debió bajar a free_basic si pasaron los 7 días.
        trial_end = sub.get("trial_ends_at")
        cierre = is_cierre_fitline_trial(sub)
        if trial_end:
            try:
                exp_dt = datetime.fromisoformat(str(trial_end).replace("Z", "+00:00"))
                if exp_dt <= datetime.now(timezone.utc):
                    return False, ("cierre_trial_expired" if cierre else "trial_expired"), 0
            except ValueError:
                pass
        else:
            return False, ("cierre_trial_expired" if cierre else "trial_expired"), 0
        return (
            True,
            "cierre_trial" if cierre else "trial",
            trial_voice_minutes_for_subscription(sub),
        )

    # Pago fallido: chat básico sí; sin minutos/plan de pago hasta cobro OK.
    if st == "past_due":
        return True, "past_due", 0

    if st in ("expired", "cancelled", "canceled"):
        return True, "free_basic", 0

    if plan_id == PlanId.FREE_BASIC.value:
        if not limits.voice_enabled:
            return True, "free_basic", 0
        return True, "ok", limits.gemini_minutes_per_day

    exp = sub.get("expires_at")
    if exp:
        try:
            exp_dt = datetime.fromisoformat(str(exp).replace("Z", "+00:00"))
            if exp_dt <= datetime.now(timezone.utc):
                return True, "free_basic", 0
        except ValueError:
            pass

    if st in ("active", "trialing"):
        minutes = supabase_db.get_usage_limit_minutes(user_id)
        if minutes <= 0:
            minutes = plan_minutes_daily(plan_id)
        if not limits.voice_enabled:
            return True, "free_basic", 0
        if minutes <= 0 and st == "active":
            minutes = plan_minutes_daily(plan_id)
        return True, "ok", minutes

    return False, "Suscripción inactiva", 0
