"""Comprobaciones de funciones incluidas en cada plan CED."""

from __future__ import annotations

from fastapi import HTTPException

from app.deps.auth import is_super_admin
from app.domain.plans import PlanId, PlanLimits, get_plan_limits, normalize_plan_id
from app.services import supabase_db
from app.services.admin_users import get_user_access

PLAN_UPGRADE_HINT = "Mejora tu plan en Precios (/pricing)."


def effective_plan_limits(user_id: str) -> tuple[PlanLimits, str, bool]:
    """
    Devuelve (límites efectivos, motivo de acceso, trial_activo).
    Trial activo usa límites Élite (voz limitada aparte en get_user_access).
    """
    profile = supabase_db.get_profile(user_id) or {}
    if is_super_admin(profile.get("email"), profile.get("role")):
        return get_plan_limits(PlanId.FOUNDING.value), "ok", False

    allowed, reason, _ = get_user_access(user_id)
    if not allowed and reason == "trial_expired":
        return get_plan_limits(PlanId.FREE_BASIC.value), "trial_expired", False

    if allowed and reason == "trial":
        return get_plan_limits(PlanId.ELITE.value), "trial", True

    sub = supabase_db.get_subscription(user_id) or {}
    plan_id = normalize_plan_id(sub.get("plan_id"))
    return get_plan_limits(plan_id), reason or ("ok" if allowed else "denied"), False


def require_pdf_reports(user_id: str) -> None:
    limits, reason, _ = effective_plan_limits(user_id)
    if reason == "trial_expired":
        raise HTTPException(
            status_code=403,
            detail="Tu prueba terminó. Elige un plan de pago o continúa con el plan Básico gratis.",
        )
    if not limits.pdf_reports:
        raise HTTPException(
            status_code=403,
            detail=f"Los PDFs requieren plan Élite o Founding. {PLAN_UPGRADE_HINT}",
        )


def require_meta_social(user_id: str) -> None:
    limits, reason, _ = effective_plan_limits(user_id)
    if reason == "trial_expired":
        raise HTTPException(
            status_code=403,
            detail="Tu prueba terminó. Elige un plan de pago para publicar en redes.",
        )
    if not limits.meta_social_enabled:
        raise HTTPException(
            status_code=403,
            detail=f"Publicar en Facebook e Instagram requiere plan Élite o Founding. {PLAN_UPGRADE_HINT}",
        )


def chat_message_limit(user_id: str) -> int:
    """Mensajes de chat permitidos hoy (-1 = ilimitado, 0 = bloqueado)."""
    profile = supabase_db.get_profile(user_id) or {}
    if is_super_admin(profile.get("email"), profile.get("role")):
        return -1

    supabase_db.expire_trial_if_needed(user_id)
    allowed, reason, _ = get_user_access(user_id)
    if not allowed and reason == "trial_expired":
        return 0

    if allowed and reason == "trial":
        return -1

    limits, _, _ = effective_plan_limits(user_id)
    return limits.claude_messages_per_day
