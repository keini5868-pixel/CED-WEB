"""Margen mínimo por plan (COGS Retell+Gemini $0.081/min + Nano Banana 2, 30 días)."""

from __future__ import annotations

from app.domain.plans import (
    MIN_PLAN_MARGIN_CIERRE_USD,
    MIN_PLAN_MARGIN_USD,
    PlanId,
    estimate_plan_monthly_margin_usd,
    estimate_plan_monthly_provider_cogs_usd,
    get_plan_limits,
)


def test_starter_limits_for_ten_dollar_margin():
    limits = get_plan_limits(PlanId.STARTER.value)
    assert limits.voice_minutes_per_day == 4
    assert limits.web_searches_per_day == 15
    assert limits.ai_images_standard_per_day == 2
    assert limits.ai_images_text_per_day == 1


def test_cierre_limits_pm_voice_budget():
    limits = get_plan_limits(PlanId.CIERRE.value)
    assert limits.voice_minutes_per_day == 6  # 180 min/mes
    assert limits.prospection_enabled is True
    assert limits.meta_social_enabled is True
    assert limits.camera_enabled is False
    assert limits.ai_images_standard_per_day == 0
    assert limits.pdf_reports is False


def test_paid_plans_guarantee_min_margin_with_bounded_web():
    for plan in (
        PlanId.STARTER,
        PlanId.PRO,
        PlanId.ELITE,
        PlanId.FOUNDING,
    ):
        margin = estimate_plan_monthly_margin_usd(plan.value)
        cogs = estimate_plan_monthly_provider_cogs_usd(plan.value)
        assert margin >= MIN_PLAN_MARGIN_USD, (
            f"{plan.value}: margin={margin} cogs={cogs} < {MIN_PLAN_MARGIN_USD}"
        )


def test_cierre_margin_with_retell_voice_cogs():
    margin = estimate_plan_monthly_margin_usd(PlanId.CIERRE.value)
    cogs = estimate_plan_monthly_provider_cogs_usd(PlanId.CIERRE.value)
    assert margin >= MIN_PLAN_MARGIN_CIERRE_USD, (
        f"cierre: margin={margin} cogs={cogs} < {MIN_PLAN_MARGIN_CIERRE_USD}"
    )


def test_starter_margin_explicit_math():
    # 4*30*0.081 + 15*30*0.008 + 2*30*0.067 + 1*30*0.034
    # = 9.72 + 3.6 + 4.02 + 1.02 = 18.36
    assert estimate_plan_monthly_provider_cogs_usd(PlanId.STARTER.value) == 18.36
    assert estimate_plan_monthly_margin_usd(PlanId.STARTER.value) == 11.64
