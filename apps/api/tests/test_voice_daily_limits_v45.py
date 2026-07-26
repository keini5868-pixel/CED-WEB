"""Tests — límites diarios de voz (Starter 5 / Pro 12 / Élite 20 / Founding 30)
y blindaje trial (5 min/día, 7 días) vs. Básico permanente post-trial (0 min).

Calibrados a margen mínimo $10/mes (COGS provider peor caso). El trial de 7
días da 5 min/día y al día 8 la voz queda en 0 (chat de texto sigue).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app.domain.plans import PlanId, get_plan_limits
from app.services.admin_users import get_user_access


def test_paid_plan_daily_voice_limits_match_new_numbers():
    assert get_plan_limits(PlanId.STARTER.value).voice_minutes_per_day == 5
    assert get_plan_limits(PlanId.PRO.value).voice_minutes_per_day == 12
    assert get_plan_limits(PlanId.ELITE.value).voice_minutes_per_day == 20
    assert get_plan_limits(PlanId.FOUNDING.value).voice_minutes_per_day == 30


def test_free_basic_permanent_never_has_voice():
    limits = get_plan_limits(PlanId.FREE_BASIC.value)
    assert limits.voice_enabled is False
    assert limits.voice_minutes_per_day == 0


def _mock_profile(_user_id: str):
    return {"email": "user@example.com", "role": "client"}


def test_trial_user_gets_five_minutes_per_day():
    trial_end = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    sub = {
        "plan_id": PlanId.STARTER.value,
        "status": "trialing",
        "trial_ends_at": trial_end,
    }
    with (
        patch("app.services.supabase_db.get_profile", side_effect=_mock_profile),
        patch("app.services.supabase_db.get_subscription", return_value=sub),
        patch("app.services.supabase_db.expire_trial_if_needed", return_value=False),
        patch("app.deps.auth.is_super_admin", return_value=False),
    ):
        allowed, reason, minutes = get_user_access("user-trial-1")
    assert allowed is True
    assert reason == "trial"
    assert minutes == 5


def test_trial_expired_after_day_seven_gets_zero_minutes():
    trial_end = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    sub = {
        "plan_id": PlanId.STARTER.value,
        "status": "trialing",
        "trial_ends_at": trial_end,
    }
    with (
        patch("app.services.supabase_db.get_profile", side_effect=_mock_profile),
        patch("app.services.supabase_db.get_subscription", return_value=sub),
        patch("app.services.supabase_db.expire_trial_if_needed", return_value=True),
        patch("app.deps.auth.is_super_admin", return_value=False),
    ):
        allowed, reason, minutes = get_user_access("user-trial-expired")
    assert allowed is False
    assert reason == "trial_expired"
    assert minutes == 0


def test_permanent_free_basic_post_trial_has_zero_voice_minutes():
    sub = {"plan_id": PlanId.FREE_BASIC.value, "status": "active"}
    with (
        patch("app.services.supabase_db.get_profile", side_effect=_mock_profile),
        patch("app.services.supabase_db.get_subscription", return_value=sub),
        patch("app.services.supabase_db.expire_trial_if_needed", return_value=False),
        patch("app.deps.auth.is_super_admin", return_value=False),
    ):
        allowed, reason, minutes = get_user_access("user-free-basic-1")
    assert allowed is True
    assert reason == "free_basic"
    assert minutes == 0


def test_expired_subscription_falls_back_to_free_basic_zero_minutes():
    sub = {"plan_id": PlanId.STARTER.value, "status": "expired"}
    with (
        patch("app.services.supabase_db.get_profile", side_effect=_mock_profile),
        patch("app.services.supabase_db.get_subscription", return_value=sub),
        patch("app.services.supabase_db.expire_trial_if_needed", return_value=False),
        patch("app.deps.auth.is_super_admin", return_value=False),
    ):
        allowed, reason, minutes = get_user_access("user-lapsed-starter")
    assert allowed is True
    assert reason == "free_basic"
    assert minutes == 0


def test_active_paid_plan_returns_new_daily_minutes():
    sub = {"plan_id": PlanId.PRO.value, "status": "active"}
    with (
        patch("app.services.supabase_db.get_profile", side_effect=_mock_profile),
        patch("app.services.supabase_db.get_subscription", return_value=sub),
        patch("app.services.supabase_db.expire_trial_if_needed", return_value=False),
        patch("app.deps.auth.is_super_admin", return_value=False),
        patch("app.services.supabase_db.get_usage_limit_minutes", return_value=12),
    ):
        allowed, reason, minutes = get_user_access("user-pro-active")
    assert allowed is True
    assert reason == "ok"
    assert minutes == 12


def test_past_due_loses_paid_voice_minutes():
    sub = {"plan_id": PlanId.ELITE.value, "status": "past_due"}
    with (
        patch("app.services.supabase_db.get_profile", side_effect=_mock_profile),
        patch("app.services.supabase_db.get_subscription", return_value=sub),
        patch("app.services.supabase_db.expire_trial_if_needed", return_value=False),
        patch("app.deps.auth.is_super_admin", return_value=False),
    ):
        allowed, reason, minutes = get_user_access("user-past-due")
    assert allowed is True
    assert reason == "past_due"
    assert minutes == 0


def test_effective_plan_limits_past_due_is_free_basic():
    from app.deps.plan_access import effective_plan_limits

    with (
        patch("app.deps.plan_access.get_user_access", return_value=(True, "past_due", 0)),
        patch("app.deps.plan_access.is_super_admin", return_value=False),
        patch("app.services.supabase_db.get_profile", side_effect=_mock_profile),
    ):
        limits, reason, trial = effective_plan_limits("user-past-due")
    assert reason == "past_due"
    assert trial is False
    assert limits.voice_enabled is False
    assert limits.meta_social_enabled is False
