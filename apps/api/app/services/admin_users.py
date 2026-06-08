"""Creación y listado de usuarios manuales — solo super admin."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from app.config import get_settings
from app.domain.plans import CED_ELITE, PLAN_PRICES_USD, PlanId
from app.services import supabase_db
from app.services.email_welcome import send_welcome_email

logger = logging.getLogger(__name__)

ACCESS_TYPES = frozenset({"paid", "beta", "founding_gift", "coadmin"})
PLAN_LABELS = {
    PlanId.ELITE_FOUNDING.value: "CED Élite Founding",
    PlanId.ELITE_REGULAR.value: "CED Élite Regular",
}
MAX_CREATIONS_PER_DAY = 10
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


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
    if plan not in (PlanId.ELITE_FOUNDING.value, PlanId.ELITE_REGULAR.value):
        raise AdminUserError("Plan inválido.")
    if minutes_daily < 1 or minutes_daily > 480:
        raise AdminUserError("Minutos diarios entre 1 y 480.")
    if initial_balance < 0:
        raise AdminUserError("Saldo inicial no puede ser negativo.")
    if email_exists(email):
        raise AdminUserError("Ya existe un usuario con ese email.")

    expires_at = _parse_expires(duration_days)
    status = _subscription_status(access_type, expires_at)
    is_founding = plan == PlanId.ELITE_FOUNDING.value
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
                "price_locked_usd": PLAN_PRICES_USD.get(
                    PlanId.ELITE_FOUNDING if is_founding else PlanId.ELITE_REGULAR,
                    35 if is_founding else 49,
                ),
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
    if st in ("expired", "cancelled"):
        return st
    exp = sub.get("expires_at")
    if exp:
        try:
            exp_dt = datetime.fromisoformat(str(exp).replace("Z", "+00:00"))
            if exp_dt <= datetime.now(timezone.utc):
                return "expired"
            if exp_dt <= datetime.now(timezone.utc) + timedelta(days=7):
                return "expiring"
        except ValueError:
            pass
    return "active"


def list_admin_users(search: str = "", limit: int = 100) -> dict[str, Any]:
    client = _client()
    query = (
        client.table("profiles")
        .select(
            "id, email, full_name, phone, role, is_founding_member, created_at, "
            "subscriptions!subscriptions_user_id_fkey(plan_id, access_type, status, expires_at, paused_at), "
            "usage_limits(minutes_daily)"
        )
        .order("created_at", desc=True)
        .limit(min(limit, 200))
    )
    if search.strip():
        term = search.strip().replace(",", " ")
        query = query.or_(f"email.ilike.%{term}%,full_name.ilike.%{term}%")

    result = query.execute()
    rows = result.data or []
    users: list[dict[str, Any]] = []
    active = expiring = 0

    for row in rows:
        subs = row.get("subscriptions") or []
        sub = subs[0] if isinstance(subs, list) and subs else subs if isinstance(subs, dict) else None
        limits = row.get("usage_limits") or []
        lim = limits[0] if isinstance(limits, list) and limits else limits if isinstance(limits, dict) else None
        status = _user_status(sub)
        if status == "active":
            active += 1
        elif status == "expiring":
            expiring += 1
            active += 1

        access = (sub or {}).get("access_type") or "paid"
        if row.get("role") == "super_admin":
            access = "admin"
        elif row.get("role") == "coadmin":
            access = "coadmin"

        users.append(
            {
                "id": row["id"],
                "email": row.get("email"),
                "full_name": row.get("full_name"),
                "phone": row.get("phone"),
                "role": row.get("role"),
                "access_type": access,
                "plan": (sub or {}).get("plan_id"),
                "status": status,
                "expires_at": (sub or {}).get("expires_at"),
                "minutes_daily": (lim or {}).get("minutes_daily") or CED_ELITE.gemini_minutes_per_day,
                "created_at": row.get("created_at"),
                "is_founding_member": row.get("is_founding_member"),
            }
        )

    return {
        "users": users,
        "total": len(users),
        "active_count": active,
        "expiring_count": expiring,
    }


def get_user_access(user_id: str) -> tuple[bool, str, int]:
    """Acceso activo + minutos diarios del plan."""
    from app.deps.auth import is_super_admin

    profile = supabase_db.get_profile(user_id)
    email = (profile or {}).get("email")
    role = (profile or {}).get("role")
    if is_super_admin(email, role if role == "super_admin" else None):
        minutes = supabase_db.get_usage_limit_minutes(user_id)
        return True, "ok", minutes

    sub = supabase_db.get_subscription(user_id)
    if not sub:
        return False, "Sin suscripción activa", CED_ELITE.gemini_minutes_per_day
    if sub.get("paused_at"):
        return False, "Cuenta pausada por administrador", CED_ELITE.gemini_minutes_per_day
    st = str(sub.get("status") or "")
    if st in ("expired", "cancelled"):
        return False, "Suscripción inactiva", CED_ELITE.gemini_minutes_per_day
    exp = sub.get("expires_at")
    if exp:
        try:
            exp_dt = datetime.fromisoformat(str(exp).replace("Z", "+00:00"))
            if exp_dt <= datetime.now(timezone.utc):
                return False, "Acceso expirado", CED_ELITE.gemini_minutes_per_day
        except ValueError:
            pass
    minutes = supabase_db.get_usage_limit_minutes(user_id)
    return True, "ok", minutes
