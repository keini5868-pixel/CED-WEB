"""Ruteo de voz: todos los planes → Retell Jarvis (stack Cierre/OpenAI retirado)."""

from __future__ import annotations

from app.domain.plans import (
    PlanId,
    plan_uses_gemini_voice_stack,
    plan_voice_transport,
)


def test_cierre_uses_retell_like_premium():
    assert plan_uses_gemini_voice_stack(PlanId.CIERRE.value) is False
    assert plan_voice_transport(PlanId.CIERRE.value) == "retell"


def test_premium_plans_use_retell_jarvis():
    for pid in (
        PlanId.STARTER.value,
        PlanId.PRO.value,
        PlanId.ELITE.value,
        PlanId.FOUNDING.value,
    ):
        assert plan_uses_gemini_voice_stack(pid) is False
        assert plan_voice_transport(pid) == "retell"
