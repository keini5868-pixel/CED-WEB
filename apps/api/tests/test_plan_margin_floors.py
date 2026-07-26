"""Margen mínimo $10/mes por plan (COGS provider peor caso, 30 días)."""

from __future__ import annotations

from app.domain.plans import (
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
    assert limits.ai_images_standard_per_day == 5
    assert limits.ai_images_text_per_day == 1


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


def test_starter_margin_explicit_math():
    # 5*30*0.06 + 15*30*0.008 + 5*30*0.01 + 1*30*0.03 = 9 + 3.6 + 1.5 + 0.9 = 15
    assert estimate_plan_monthly_provider_cogs_usd(PlanId.STARTER.value) == 15.0
    assert estimate_plan_monthly_margin_usd(PlanId.STARTER.value) == 15.0
