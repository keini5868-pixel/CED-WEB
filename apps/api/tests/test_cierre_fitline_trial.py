"""Trial FitLine / CED PM International: pool único 15 min en 24 h (sin renovar)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app.domain.plans import (
    CIERRE_TRIAL_VOICE_MINUTES,
    PlanId,
    TRIAL_VOICE_MINUTES_PER_DAY,
    VOICE_TRIAL_MINUTES,
    is_cierre_fitline_trial,
    is_voice_pool_trial,
    trial_voice_minutes_for_subscription,
)
from app.services.admin_users import get_user_access
from app.services.supabase_db import cierre_trial_window_start


def _mock_profile(_user_id: str):
    return {"email": "fitline@example.com", "role": "client"}


def test_cierre_trial_minutes_helper():
    sub = {"plan_id": "cierre", "status": "trialing"}
    assert is_cierre_fitline_trial(sub) is True
    assert trial_voice_minutes_for_subscription(sub) == CIERRE_TRIAL_VOICE_MINUTES
    assert CIERRE_TRIAL_VOICE_MINUTES == 15
    assert trial_voice_minutes_for_subscription(
        {"plan_id": "elite", "status": "trialing"}
    ) == TRIAL_VOICE_MINUTES_PER_DAY


def test_cierre_trial_window_start_is_24h_before_end():
    ends = datetime(2026, 8, 12, 18, 0, tzinfo=timezone.utc)
    sub = {
        "plan_id": "cierre",
        "status": "trialing",
        "trial_ends_at": ends.isoformat(),
    }
    start = cierre_trial_window_start(sub)
    assert start is not None
    assert start == ends - timedelta(hours=24)


def test_cierre_fitline_trial_gets_15_minutes():
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
    assert minutes == 15


def test_cierre_trial_voice_state_uses_window_pool_not_daily_renew():
    """Si ya usó 15 min en la ventana, queda bloqueado aunque «hoy» sea otro día."""
    from app.services.voice_usage import voice_access_state

    now = datetime.now(timezone.utc)
    trial_end = (now + timedelta(hours=10)).isoformat()
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
        patch("app.deps.auth.is_staff_admin", return_value=False),
        patch("app.services.supabase_db.get_usage_minutes_today", return_value=0.0),
        patch(
            "app.services.supabase_db.get_cierre_trial_used_minutes", return_value=15.0
        ),
        patch("app.services.supabase_db.get_recharge_balance_usd", return_value=0.0),
    ):
        state = voice_access_state("user-cierre-pool")
    assert state["access_message"] == "cierre_trial"
    assert state["plan_minutes_daily"] == 15
    assert state["used_minutes_today"] == 15.0
    assert state["blocked"] is True
    assert state["quota_exhausted"] is True


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
    """Trials legacy de 7 días (created→ends ≈ 7 d) siguen con 5 min/día."""
    now = datetime.now(timezone.utc)
    created = (now - timedelta(days=4)).isoformat()
    trial_end = (now + timedelta(days=3)).isoformat()
    sub = {
        "plan_id": PlanId.ELITE.value,
        "status": "trialing",
        "created_at": created,
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
    assert is_voice_pool_trial(sub) is False


def test_new_general_signup_gets_15_minute_24h_pool():
    """Altas nuevas (elite + ventana 24 h) reciben pool 15 min, no 5/día."""
    now = datetime.now(timezone.utc)
    created = (now - timedelta(hours=2)).isoformat()
    trial_end = (now + timedelta(hours=22)).isoformat()
    sub = {
        "plan_id": PlanId.ELITE.value,
        "status": "trialing",
        "created_at": created,
        "trial_ends_at": trial_end,
    }
    assert is_voice_pool_trial(sub) is True
    assert trial_voice_minutes_for_subscription(sub) == VOICE_TRIAL_MINUTES
    with (
        patch("app.services.supabase_db.get_profile", side_effect=_mock_profile),
        patch("app.services.supabase_db.get_subscription", return_value=sub),
        patch("app.services.supabase_db.expire_trial_if_needed", return_value=False),
        patch("app.deps.auth.is_super_admin", return_value=False),
    ):
        allowed, reason, minutes = get_user_access("user-new-24h-trial")
    assert allowed is True
    assert reason == "trial"
    assert minutes == 15


def test_general_24h_trial_voice_state_uses_window_pool_not_daily_renew():
    from app.services.voice_usage import voice_access_state

    now = datetime.now(timezone.utc)
    sub = {
        "plan_id": PlanId.ELITE.value,
        "status": "trialing",
        "created_at": (now - timedelta(hours=6)).isoformat(),
        "trial_ends_at": (now + timedelta(hours=18)).isoformat(),
    }
    with (
        patch("app.services.supabase_db.get_profile", side_effect=_mock_profile),
        patch("app.services.supabase_db.get_subscription", return_value=sub),
        patch("app.services.supabase_db.expire_trial_if_needed", return_value=False),
        patch("app.deps.auth.is_super_admin", return_value=False),
        patch("app.deps.auth.is_staff_admin", return_value=False),
        patch("app.services.supabase_db.get_usage_minutes_today", return_value=0.0),
        patch(
            "app.services.supabase_db.get_cierre_trial_used_minutes", return_value=15.0
        ),
        patch("app.services.supabase_db.get_recharge_balance_usd", return_value=0.0),
    ):
        state = voice_access_state("user-general-pool")
    assert state["access_message"] == "trial"
    assert state["plan_minutes_daily"] == 15
    assert state["used_minutes_today"] == 15.0
    assert state["blocked"] is True
    assert state["voice_pool_trial"] is True


def test_legacy_seven_day_trial_last_day_stays_five_minutes():
    """Un trial de 7 días con <26 h restantes NO se convierte a pool de 15."""
    now = datetime.now(timezone.utc)
    sub = {
        "plan_id": PlanId.ELITE.value,
        "status": "trialing",
        "created_at": (now - timedelta(days=6, hours=12)).isoformat(),
        "trial_ends_at": (now + timedelta(hours=12)).isoformat(),
    }
    assert is_voice_pool_trial(sub) is False
    assert trial_voice_minutes_for_subscription(sub) == TRIAL_VOICE_MINUTES_PER_DAY


def test_armed_trial_waits_until_first_voice_use():
    """Sin primer uso: 15 min disponibles y el reloj de 24 h no corre."""
    now = datetime.now(timezone.utc)
    sub = {
        "plan_id": PlanId.ELITE.value,
        "status": "trialing",
        "voice_trial_armed": True,
        "voice_trial_started_at": None,
        "created_at": (now - timedelta(days=2)).isoformat(),
        "trial_ends_at": (now + timedelta(days=5)).isoformat(),
    }
    assert is_voice_pool_trial(sub) is True
    assert cierre_trial_window_start(sub) is None
    assert trial_voice_minutes_for_subscription(sub) == VOICE_TRIAL_MINUTES
    with (
        patch("app.services.supabase_db.get_profile", side_effect=_mock_profile),
        patch("app.services.supabase_db.get_subscription", return_value=sub),
        patch("app.services.supabase_db.expire_trial_if_needed", return_value=False),
        patch("app.deps.auth.is_super_admin", return_value=False),
    ):
        allowed, reason, minutes = get_user_access("user-armed-waiting")
    assert allowed is True
    assert reason == "trial"
    assert minutes == 15


def test_voice_clock_expires_24h_after_first_use_not_registration():
    """Tras el primer uso, a las 24 h se corta la voz; el trial de 7 días sigue."""
    now = datetime.now(timezone.utc)
    sub = {
        "plan_id": PlanId.ELITE.value,
        "status": "trialing",
        "voice_trial_armed": True,
        "voice_trial_started_at": (now - timedelta(hours=25)).isoformat(),
        "created_at": (now - timedelta(days=1)).isoformat(),
        "trial_ends_at": (now + timedelta(days=6)).isoformat(),
    }
    with (
        patch("app.services.supabase_db.get_profile", side_effect=_mock_profile),
        patch("app.services.supabase_db.get_subscription", return_value=sub),
        patch("app.services.supabase_db.expire_trial_if_needed", return_value=False),
        patch("app.deps.auth.is_super_admin", return_value=False),
    ):
        allowed, reason, minutes = get_user_access("user-voice-clock-done")
    assert allowed is True
    assert reason == "voice_trial_expired"
    assert minutes == 0


def test_voice_trial_expired_still_gets_elite_images():
    from app.deps.plan_access import effective_plan_limits

    now = datetime.now(timezone.utc)
    sub = {
        "plan_id": PlanId.ELITE.value,
        "status": "trialing",
        "voice_trial_armed": True,
        "voice_trial_started_at": (now - timedelta(hours=25)).isoformat(),
        "trial_ends_at": (now + timedelta(days=5)).isoformat(),
    }
    with (
        patch("app.services.supabase_db.get_profile", side_effect=_mock_profile),
        patch("app.services.supabase_db.get_subscription", return_value=sub),
        patch("app.services.supabase_db.expire_trial_if_needed", return_value=False),
        patch("app.deps.auth.is_super_admin", return_value=False),
        patch("app.deps.plan_access.is_super_admin", return_value=False),
    ):
        limits, reason, trial = effective_plan_limits("user-voice-done-images-ok")
    assert trial is True
    assert reason == "voice_trial_expired"
    assert limits.ai_images_standard_per_day == 14
    assert limits.pdf_reports is True
    assert limits.voice_minutes_per_day == 12  # élite; la voz ya está gated aparte


def test_minutes_exhausted_before_24h_blocks_voice():
    from app.services.voice_usage import voice_access_state

    now = datetime.now(timezone.utc)
    sub = {
        "plan_id": PlanId.ELITE.value,
        "status": "trialing",
        "voice_trial_armed": True,
        "voice_trial_started_at": (now - timedelta(hours=1)).isoformat(),
        "trial_ends_at": (now + timedelta(days=6)).isoformat(),
    }
    with (
        patch("app.services.supabase_db.get_profile", side_effect=_mock_profile),
        patch("app.services.supabase_db.get_subscription", return_value=sub),
        patch("app.services.supabase_db.expire_trial_if_needed", return_value=False),
        patch("app.deps.auth.is_super_admin", return_value=False),
        patch("app.deps.auth.is_staff_admin", return_value=False),
        patch("app.services.supabase_db.get_usage_minutes_today", return_value=0.0),
        patch(
            "app.services.supabase_db.get_cierre_trial_used_minutes", return_value=15.0
        ),
        patch("app.services.supabase_db.get_recharge_balance_usd", return_value=0.0),
    ):
        state = voice_access_state("user-minutes-first")
    assert state["access_message"] == "trial"
    assert state["blocked"] is True
    assert state["quota_exhausted"] is True
    assert state["voice_pool_trial"] is True
