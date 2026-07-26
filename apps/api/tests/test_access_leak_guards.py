"""Guards: trial vencido auto-downgrade + past_due sin funciones de pago."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app.domain.plans import PlanId
from app.services.chat_multimedia import _effective_plan_key
from app.services.supabase_db import expire_trial_if_needed


def test_expire_trial_auto_downgrades_without_stripe():
    trial_end = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    sub = {
        "plan_id": PlanId.ELITE.value,
        "status": "trialing",
        "trial_ends_at": trial_end,
        "stripe_subscription_id": None,
    }
    with (
        patch("app.services.supabase_db.get_subscription", return_value=sub),
        patch("app.services.supabase_db.downgrade_to_free_basic") as downgrade,
    ):
        assert expire_trial_if_needed("u-expired") is True
        downgrade.assert_called_once_with("u-expired")


def test_expire_trial_skips_active_trial():
    trial_end = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    sub = {
        "plan_id": PlanId.ELITE.value,
        "status": "trialing",
        "trial_ends_at": trial_end,
    }
    with (
        patch("app.services.supabase_db.get_subscription", return_value=sub),
        patch("app.services.supabase_db.downgrade_to_free_basic") as downgrade,
    ):
        assert expire_trial_if_needed("u-trial") is False
        downgrade.assert_not_called()


def test_chat_multimedia_plan_key_not_elite_when_trial_expired():
    with (
        patch(
            "app.services.admin_users.get_user_access",
            return_value=(False, "trial_expired", 0),
        ),
        patch("app.services.chat_multimedia.is_super_admin", return_value=False),
        patch(
            "app.services.supabase_db.get_profile",
            return_value={"email": "a@b.com", "role": "client"},
        ),
    ):
        assert _effective_plan_key("u1") == "free_basic"


def test_chat_multimedia_plan_key_past_due_is_free_basic():
    with (
        patch(
            "app.services.admin_users.get_user_access",
            return_value=(True, "past_due", 0),
        ),
        patch("app.services.chat_multimedia.is_super_admin", return_value=False),
        patch(
            "app.services.supabase_db.get_profile",
            return_value={"email": "a@b.com", "role": "client"},
        ),
    ):
        assert _effective_plan_key("u2") == "free_basic"
