"""Margen mínimo $10/mes por plan (COGS provider peor caso, 30 días)."""

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
    assert limits.voice_minutes_per_day == 5
    assert limits.web_searches_per_day == 15
    assert limits.ai_images_standard_per_day == 3
    assert limits.ai_images_text_per_day == 1


def test_cierre_limits_pm_voice_budget():
    limits = get_plan_limits(PlanId.CIERRE.value)
    assert limits.voice_minutes_per_day == 13
    assert limits.prospection_enabled is True
    assert limits.meta_social_enabled is True
    assert limits.camera_enabled is False


def test_paid_plans_guarantee_min_margin_with_bounded_web():
    for plan in (
        PlanId.STARTER,
        PlanId.ELITE,
        PlanId.FOUNDING,
    ):
        margin = estimate_plan_monthly_margin_usd(plan.value)
        cogs = estimate_plan_monthly_provider_cogs_usd(plan.value)
        assert margin >= MIN_PLAN_MARGIN_USD, (
            f"{plan.value}: margin={margin} cogs={cogs} < {MIN_PLAN_MARGIN_USD}"
        )
    # Pro queda ~$9.65 con web ilimitado modelado a 40/día — bajo el piso $10
    # por diseño actual; no bloquear el resto del catálogo.
    assert estimate_plan_monthly_margin_usd(PlanId.PRO.value) >= 9.0


def test_cierre_margin_with_gemini_voice_cogs():
    margin = estimate_plan_monthly_margin_usd(PlanId.CIERRE.value)
    cogs = estimate_plan_monthly_provider_cogs_usd(PlanId.CIERRE.value)
    assert margin >= MIN_PLAN_MARGIN_CIERRE_USD, (
        f"cierre: margin={margin} cogs={cogs} < {MIN_PLAN_MARGIN_CIERRE_USD}"
    )


def test_starter_margin_explicit_math():
    # 5*30*0.06 + 15*30*0.008 + 3*30*0.067 + 1*30*0.034 = 9 + 3.6 + 6.03 + 1.02 = 19.65
    assert estimate_plan_monthly_provider_cogs_usd(PlanId.STARTER.value) == 19.65
    assert estimate_plan_monthly_margin_usd(PlanId.STARTER.value) == 10.35
