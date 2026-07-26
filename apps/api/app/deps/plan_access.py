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

    if allowed and reason in ("free_basic", "past_due"):
        return get_plan_limits(PlanId.FREE_BASIC.value), reason, False

    if allowed and reason == "trial":
        return get_plan_limits(PlanId.ELITE.value), "trial", True

    sub = supabase_db.get_subscription(user_id) or {}
    if str(sub.get("status") or "") == "past_due":
        return get_plan_limits(PlanId.FREE_BASIC.value), "past_due", False

    plan_id = normalize_plan_id(sub.get("plan_id"))
    return get_plan_limits(plan_id), reason or ("ok" if allowed else "denied"), False


def pdf_included_in_plan_today(user_id: str, limits: PlanLimits) -> bool:
    """True si el siguiente PDF de hoy está cubierto por el plan (sin monedero).

    Planes pagados: pdf_reports_per_day=-1 (ilimitado, sin cambio de comportamiento).
    Básico gratis: pdf_reports_per_day=1 — cuenta lo ya generado HOY antes de este
    turno; una vez alcanzado el tope, cae a monedero igual que un plan sin PDF.
    """
    if not limits.pdf_reports:
        return False
    if limits.pdf_reports_per_day < 0:
        return True
    from app.services.supabase_db import count_pdfs_today

    return count_pdfs_today(user_id) < limits.pdf_reports_per_day


def require_pdf_reports(user_id: str) -> bool:
    """Verifica cupo de PDF. Retorna True si el PDF de este turno va incluido en el
    plan (no cobrar monedero después) — el llamador debe pasar ese valor a
    `charge_pdf_from_wallet_if_needed` para no recontar tras guardar el artefacto."""
    limits, reason, _ = effective_plan_limits(user_id)
    included = pdf_included_in_plan_today(user_id, limits)
    if included:
        return True
    from app.services.wallet import can_afford

    if can_afford(user_id, "pdf", units=1.0):
        return False
    if reason == "trial_expired":
        detail = "Tu prueba terminó. Elige un plan o recarga desde $10 para PDF."
    elif limits.pdf_reports:
        detail = (
            f"Alcanzaste tu límite diario de {limits.pdf_reports_per_day} PDF gratis. "
            "Recarga desde $10 para seguir generando PDFs hoy."
        )
    else:
        detail = (
            "Los PDFs requieren plan Pro, Élite o Founding, o recarga desde $10. "
            f"{PLAN_UPGRADE_HINT}"
        )
    raise HTTPException(status_code=402, detail=detail)


def charge_pdf_from_wallet_if_needed(user_id: str, *, included_in_plan: bool) -> None:
    """Tras PDF exitoso: si no estaba incluido en el plan/tope de hoy, debita monedero."""
    if included_in_plan:
        return
    profile = supabase_db.get_profile(user_id) or {}
    if is_super_admin(profile.get("email"), profile.get("role")):
        return
    from app.services.wallet import try_spend

    spend = try_spend(user_id, "pdf", units=1.0)
    if not spend.get("ok"):
        raise HTTPException(
            status_code=402,
            detail=spend.get("error") or "Recarga desde $10 para generar PDF.",
        )


def require_meta_social(user_id: str) -> None:
    limits, reason, _ = effective_plan_limits(user_id)
    if reason == "trial_expired":
        raise HTTPException(
            status_code=403,
            detail="Tu prueba terminó. Elige un plan de pago para publicar en redes.",
        )
    if reason == "past_due":
        raise HTTPException(
            status_code=403,
            detail="Hay un pago pendiente. Actualiza tu método de pago para publicar en redes.",
        )
    if not limits.meta_social_enabled:
        raise HTTPException(
            status_code=403,
            detail=f"Publicar en Facebook e Instagram requiere plan Pro, Élite o Founding. {PLAN_UPGRADE_HINT}",
        )


def chat_message_limit(user_id: str, *, profile: dict | None = None) -> int:
    """Mensajes de chat permitidos hoy (-1 = ilimitado, 0 = bloqueado)."""
    profile = profile if profile is not None else (supabase_db.get_profile(user_id) or {})
    if is_super_admin(profile.get("email"), profile.get("role")):
        return -1

    supabase_db.expire_trial_if_needed(user_id)
    allowed, reason, _ = get_user_access(user_id)
    if not allowed and reason == "trial_expired":
        return get_plan_limits(PlanId.FREE_BASIC.value).claude_messages_per_day

    if allowed and reason == "trial":
        return -1

    limits, _, _ = effective_plan_limits(user_id)
    return limits.claude_messages_per_day
