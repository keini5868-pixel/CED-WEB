"""Cupos privacidad: CED incluido + Sentinel volumen (max)."""

from __future__ import annotations

from app.domain.privacy_seal_entitlement import resolve_privacy_seal_entitlement
from app.domain.plans import PlanId


def test_founding_includes_200_seals_without_sentinel_row():
    ent = resolve_privacy_seal_entitlement(
        allowed=True,
        reason="ok",
        ced_plan_id=PlanId.FOUNDING.value,
        sentinel_row=None,
        privacy_seals_used=0,
    )
    assert ent["active"] is True
    assert ent["seals_per_month"] == 200
    assert ent["ced_included_cap"] == 200
    assert ent["sentinel_addon_cap"] == 0


def test_pro_plus_sentinel_uses_max_not_sum():
    ent = resolve_privacy_seal_entitlement(
        allowed=True,
        reason="ok",
        ced_plan_id=PlanId.PRO.value,
        sentinel_row={
            "status": "active",
            "plan_id": "sentinel_business",
            "seals_per_month": 200,
        },
        privacy_seals_used=10,
    )
    assert ent["seals_per_month"] == 200
    assert ent["ced_included_cap"] == 15
    assert ent["seals_remaining"] == 190


def test_free_basic_no_entitlement():
    ent = resolve_privacy_seal_entitlement(
        allowed=True,
        reason="free_basic",
        ced_plan_id=PlanId.FREE_BASIC.value,
        sentinel_row=None,
        privacy_seals_used=0,
    )
    assert ent["active"] is False
    assert ent["seals_per_month"] == 0
