"""Tests — voice_access_state degradación graceful."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.deps.auth import require_auth_user
from app.main import create_app
from app.services.voice_usage import degraded_voice_access_state, voice_access_state


def test_degraded_voice_access_state_never_blocks():
    state = degraded_voice_access_state(reason="Connection reset")
    assert state["blocked"] is False
    assert state["access_denied"] is False
    assert state["degraded"] is True


def test_voice_access_state_returns_degraded_on_supabase_failure():
    with patch(
        "app.services.voice_usage.get_user_access",
        side_effect=Exception("postgrest timeout"),
    ):
        state = voice_access_state("user-abc-123")
    assert state["degraded"] is True
    assert state["blocked"] is False


def test_usage_balance_returns_200_when_state_degraded():
    app = create_app()
    app.dependency_overrides[require_auth_user] = lambda: {
        "id": "550e8400-e29b-41d4-a716-446655440099",
        "email": "user@test.com",
        "role": None,
    }
    client = TestClient(app, raise_server_exceptions=False)

    with patch(
        "app.routers.usage.voice_access_state_async",
        return_value=degraded_voice_access_state(reason="simulated"),
    ):
        response = client.get(
            "/v1/usage/balance",
            headers={"Authorization": "Bearer fake"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body.get("degraded") is True
    assert body.get("blocked") is False


def test_staff_unlimited_from_jwt_email_when_profile_empty():
    with (
        patch("app.services.supabase_db.get_profile", return_value={}),
        patch("app.services.supabase_db.get_subscription", return_value=None),
        patch(
            "app.deps.auth.is_staff_admin",
            side_effect=lambda email, role=None: (email or "").lower() == "keini5868@gmail.com",
        ),
    ):
        state = voice_access_state(
            "user-admin",
            email="keini5868@gmail.com",
            role=None,
        )
    assert state.get("staff_unlimited") is True
    assert state["blocked"] is False
    assert state["plan_minutes_daily"] == 99_999
    assert state.get("degraded") is not True
