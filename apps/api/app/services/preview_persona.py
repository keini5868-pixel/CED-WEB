"""Preview persona — admin simula socio nuevo plan Cierre ($20 FitLine).

Header: X-CED-Preview-As: cierre
Solo se honra si el usuario es admin/coadmin/super_admin.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Any

logger = logging.getLogger(__name__)

PREVIEW_CIERRE = "cierre"
HEADER_NAME = "x-ced-preview-as"

_preview_as: ContextVar[str] = ContextVar("ced_preview_as", default="")


def set_preview_as(value: str | None) -> None:
    _preview_as.set((value or "").strip().lower())


def get_preview_as() -> str:
    return (_preview_as.get() or "").strip().lower()


def reset_preview_as(token: Any) -> None:
    _preview_as.reset(token)


def bind_preview_as(value: str | None) -> Any:
    return _preview_as.set((value or "").strip().lower())


def user_may_use_preview(user_id: str) -> bool:
    uid = (user_id or "").strip()
    if not uid:
        return False
    try:
        from app.deps.auth import is_super_admin
        from app.services import supabase_db

        profile = supabase_db.get_profile(uid) or {}
        role = str(profile.get("role") or "").strip().lower()
        if role in ("super_admin", "coadmin", "admin"):
            return True
        return is_super_admin(profile.get("email"), profile.get("role"))
    except Exception:  # noqa: BLE001
        return False


def is_cierre_partner_preview(user_id: str | None = None) -> bool:
    """True cuando el admin pide ver CED como socio nuevo plan Cierre."""
    if get_preview_as() != PREVIEW_CIERRE:
        return False
    uid = (user_id or "").strip()
    if not uid:
        return False
    ok = user_may_use_preview(uid)
    if ok:
        logger.info("[PREVIEW] cierre partner mode user=%s", uid[:8])
    return ok


def effective_plan_id_for_voice(user_id: str, real_plan_id: str | None) -> str:
    if is_cierre_partner_preview(user_id):
        from app.domain.plans import PlanId

        return PlanId.CIERRE.value
    return (real_plan_id or "").strip().lower()
