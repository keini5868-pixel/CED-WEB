"""Cupos de sellos: incluidos en plan CED + opcional Sentinel volumen (max, no suma)."""

from __future__ import annotations

from typing import Any

from app.domain.plans import (
    CED_INCLUDED_PRIVACY_SEALS_PER_MONTH,
    PlanId,
    ced_included_privacy_seals_per_month,
    normalize_plan_id,
)
from app.domain.sentinel_privacy_plans import SENTINEL_SEALS_PER_MONTH

_ACTIVE_SENTINEL_STATUSES = frozenset({"active", "trialing", "past_due"})


def _ced_plan_grants_included_seals(*, allowed: bool, reason: str, plan_id: str) -> int:
    if not allowed or reason != "ok":
        return 0
    pid = normalize_plan_id(plan_id)
    if pid == PlanId.FREE_BASIC.value:
        return 0
    return ced_included_privacy_seals_per_month(pid)


def _sentinel_addon_cap(sentinel_row: dict[str, Any] | None) -> tuple[int, bool]:
    if not sentinel_row:
        return 0, False
    status = str(sentinel_row.get("status") or "")
    if status not in _ACTIVE_SENTINEL_STATUSES:
        return 0, False
    cap = int(sentinel_row.get("seals_per_month") or 0)
    if cap <= 0:
        pid = str(sentinel_row.get("plan_id") or "")
        cap = int(SENTINEL_SEALS_PER_MONTH.get(pid, 0))
    return cap, True


def resolve_privacy_seal_entitlement(
    *,
    allowed: bool,
    reason: str,
    ced_plan_id: str,
    sentinel_row: dict[str, Any] | None,
    privacy_seals_used: int,
    is_super_admin: bool = False,
) -> dict[str, Any]:
    """Calcula cupo unificado (techo = max(CED incluido, Sentinel activo))."""
    ced_cap = (
        max(CED_INCLUDED_PRIVACY_SEALS_PER_MONTH.values())
        if is_super_admin
        else _ced_plan_grants_included_seals(
            allowed=allowed, reason=reason, plan_id=ced_plan_id
        )
    )
    sent_cap, sent_active = _sentinel_addon_cap(sentinel_row)
    cap = max(ced_cap, sent_cap)
    used = max(0, int(privacy_seals_used or 0))
    has_entitlement = cap > 0 and (is_super_admin or ced_cap > 0 or sent_active)
    remaining = max(0, cap - used) if has_entitlement else 0

    plan_id: str | None = None
    if sent_active and sent_cap >= ced_cap:
        plan_id = str(sentinel_row.get("plan_id") or "") if sentinel_row else None
    elif ced_cap > 0:
        plan_id = normalize_plan_id(ced_plan_id)

    return {
        "active": has_entitlement,
        "plan_id": plan_id,
        "seals_per_month": cap,
        "seals_used_in_period": used,
        "seals_remaining": remaining,
        "ced_included_cap": ced_cap,
        "sentinel_addon_cap": sent_cap,
        "period_end": (sentinel_row or {}).get("period_end"),
        "status": (sentinel_row or {}).get("status") if sent_active else reason,
    }
