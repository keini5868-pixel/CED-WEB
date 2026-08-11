"""Trial FitLine / CED Cierre: 20 min en 24 h, luego pagar."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app.domain.plans import (
    CIERRE_TRIAL_VOICE_MINUTES,
    PlanId,
    TRIAL_VOICE_MINUTES_PER_DAY,
    is_cierre_fitline_trial,
    trial_voice_minutes_for_subscription,
)
from app.services.admin_users import get_user_access


def _mock_profile(_user_id: str):
    return {"email": "fitline@example.com", "role": "client"}


def test_cierre_trial_minutes_helper():
    sub = {"plan_id": "cierre", "status": "trialing"}
    assert is_cierre_fitline_trial(sub) is True
    assert trial_voice_minutes_for_subscription(sub) == CIERRE_TRIAL_VOICE_MINUTES
    assert trial_voice_minutes_for_subscription(
        {"plan_id": "elite", "status": "trialing"}
    ) == TRIAL_VOICE_MINUTES_PER_DAY


def test_cierre_fitline_trial_gets_20_minutes():
    trial_end = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()
    sub = {
        "plan_id": PlanId.CIERRE.value,
        "status": "trialing",
        "trial_ends_at": trial_end,
    }
    with (
        patch("app.services.supabase_db.get_profile", side_effect=_mock_profile),
        patch("app.services.supabase_db.get_subscription", return_value=sub),
        patch("app.services.supabase_db.expire_trial_if_needed", return_value=False),
        patch("app.deps.auth.is_super_admin", return_value=False),
    ):
        allowed, reason, minutes = get_user_access("user-cierre-trial")
    assert allowed is True
    assert reason == "cierre_trial"
    assert minutes == 20


def test_cierre_fitline_trial_expires_after_24h():
    trial_end = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    sub = {
        "plan_id": PlanId.CIERRE.value,
        "status": "trialing",
        "trial_ends_at": trial_end,
    }
    with (
        patch("app.services.supabase_db.get_profile", side_effect=_mock_profile),
        patch("app.services.supabase_db.get_subscription", return_value=sub),
        patch("app.services.supabase_db.expire_trial_if_needed", return_value=True),
        patch("app.deps.auth.is_super_admin", return_value=False),
    ):
        allowed, reason, minutes = get_user_access("user-cierre-expired")
    assert allowed is False
    assert reason == "cierre_trial_expired"
    assert minutes == 0


def test_normal_trial_still_five_minutes():
    trial_end = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    sub = {
        "plan_id": PlanId.ELITE.value,
        "status": "trialing",
        "trial_ends_at": trial_end,
    }
    with (
        patch("app.services.supabase_db.get_profile", side_effect=_mock_profile),
        patch("app.services.supabase_db.get_subscription", return_value=sub),
        patch("app.services.supabase_db.expire_trial_if_needed", return_value=False),
        patch("app.deps.auth.is_super_admin", return_value=False),
    ):
        allowed, reason, minutes = get_user_access("user-normal-trial")
    assert allowed is True
    assert reason == "trial"
    assert minutes == 5
