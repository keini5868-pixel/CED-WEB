"""Tests — Básico gratis permanente: imágenes y PDF con tope diario bajo.

Decisión (Keini, 2026-07-18): imágenes y PDF quedan disponibles de forma
PERMANENTE en el plan Básico gratis (antes: 0, requería trial o plan pagado),
como muestra continua de las capacidades de CED. Tope diario para evitar
abuso: 2 imágenes estándar/día, 1 PDF/día. Los planes pagados no cambian.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.deps.plan_access import pdf_included_in_plan_today
from app.domain.plans import PlanId, get_plan_limits


def test_free_basic_now_permanently_includes_two_std_images_per_day():
    limits = get_plan_limits(PlanId.FREE_BASIC.value)
    assert limits.ai_images_standard_per_day == 2
    assert limits.ai_images_hd_per_day == 0  # HD sigue reservado a planes pagados


def test_free_basic_now_permanently_includes_pdf_with_daily_cap():
    limits = get_plan_limits(PlanId.FREE_BASIC.value)
    assert limits.pdf_reports is True
    assert limits.pdf_reports_per_day == 1


def test_paid_plans_pdf_still_unlimited_no_regression():
    # Starter no incluye PDF (sin cambios); Pro/Élite/Founding lo tienen
    # ilimitado (sin cambios) — solo Básico gratis se movió a un tope diario.
    assert get_plan_limits(PlanId.STARTER.value).pdf_reports is False
    for plan_id in (PlanId.PRO, PlanId.ELITE, PlanId.FOUNDING):
        limits = get_plan_limits(plan_id.value)
        assert limits.pdf_reports is True
        assert limits.pdf_reports_per_day == -1, f"{plan_id} debería seguir ilimitado"


def test_paid_plans_image_caps_unchanged():
    # Starter=20/0, Pro=45/5, Elite=95/15, Founding=145/25 — no deben moverse
    # por el cambio de Básico.
    assert get_plan_limits(PlanId.STARTER.value).ai_images_standard_per_day == 20
    assert get_plan_limits(PlanId.PRO.value).ai_images_standard_per_day == 45
    assert get_plan_limits(PlanId.ELITE.value).ai_images_standard_per_day == 95
    assert get_plan_limits(PlanId.FOUNDING.value).ai_images_standard_per_day == 145


def test_pdf_included_today_true_when_under_cap():
    limits = get_plan_limits(PlanId.FREE_BASIC.value)
    with patch("app.services.supabase_db.count_pdfs_today", return_value=0):
        assert pdf_included_in_plan_today("user-x", limits) is True


def test_pdf_included_today_false_when_cap_reached():
    limits = get_plan_limits(PlanId.FREE_BASIC.value)
    with patch("app.services.supabase_db.count_pdfs_today", return_value=1):
        assert pdf_included_in_plan_today("user-x", limits) is False


def test_pdf_included_today_always_true_for_unlimited_plan():
    limits = get_plan_limits(PlanId.ELITE.value)
    # Ni siquiera debería llamar a count_pdfs_today — atajo por -1.
    with patch("app.services.supabase_db.count_pdfs_today", side_effect=AssertionError):
        assert pdf_included_in_plan_today("user-elite", limits) is True


def test_pdf_included_today_false_when_plan_has_no_pdf_at_all():
    fake_limits = MagicMock(pdf_reports=False)
    assert pdf_included_in_plan_today("user-y", fake_limits) is False


def test_require_pdf_reports_returns_true_and_no_charge_under_cap():
    from app.deps.plan_access import require_pdf_reports

    limits = get_plan_limits(PlanId.FREE_BASIC.value)
    with (
        patch(
            "app.deps.plan_access.effective_plan_limits",
            return_value=(limits, "ok", False),
        ),
        patch("app.services.supabase_db.count_pdfs_today", return_value=0),
    ):
        included = require_pdf_reports("user-basic-1")
    assert included is True


def test_require_pdf_reports_raises_with_honest_daily_cap_message_when_exhausted():
    from fastapi import HTTPException

    from app.deps.plan_access import require_pdf_reports

    limits = get_plan_limits(PlanId.FREE_BASIC.value)
    with (
        patch(
            "app.deps.plan_access.effective_plan_limits",
            return_value=(limits, "ok", False),
        ),
        patch("app.services.supabase_db.count_pdfs_today", return_value=1),
        patch("app.services.wallet.can_afford", return_value=False),
    ):
        try:
            require_pdf_reports("user-basic-2")
            raise AssertionError("debería haber lanzado HTTPException")
        except HTTPException as exc:
            assert exc.status_code == 402
            assert "límite diario" in exc.detail.lower()
            assert "1 pdf" in exc.detail.lower()
