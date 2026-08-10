"""Admin panel — trial vs paid plan labels (solo display, no muta usuarios)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.domain.plans import PlanId, TRIAL_VOICE_MINUTES_PER_DAY
from app.services.admin_users import _plan_display, _user_status


def test_trial_shows_trial_label_and_trial_ends_at():
    end = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
    sub = {
        "plan_id": PlanId.ELITE.value,
        "status": "trialing",
        "trial_ends_at": end,
        "expires_at": None,
        "stripe_subscription_id": None,
    }
    info = _plan_display(sub)
    assert info["is_trial"] is True
    assert info["is_paid"] is False
    assert info["plan_label"].startswith("Trial ·")
    assert "Élite" in info["plan_label"] or "Elite" in info["plan_label"]
    assert info["display_expires_at"] == end
    assert info["voice_minutes_daily"] == TRIAL_VOICE_MINUTES_PER_DAY
    assert _user_status(sub) == "trial"


def test_paid_elite_shows_confirmed_not_trial():
    sub = {
        "plan_id": PlanId.ELITE.value,
        "status": "active",
        "trial_ends_at": None,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        "stripe_subscription_id": "sub_abc",
    }
    info = _plan_display(sub)
    assert info["is_trial"] is False
    assert info["is_paid"] is True
    assert info["plan_label"] == "CED Élite"
    assert info["display_expires_at"] == sub["expires_at"]
    assert _user_status(sub) == "active"


def test_free_basic_post_trial_label():
    sub = {
        "plan_id": PlanId.FREE_BASIC.value,
        "status": "active",
        "trial_ends_at": None,
        "expires_at": None,
        "stripe_subscription_id": None,
    }
    info = _plan_display(sub)
    assert info["is_trial"] is False
    assert info["is_paid"] is False
    assert "Básico" in info["plan_label"]
    assert info["voice_minutes_daily"] == 0
