"""Tests — voice_access_state degradación graceful."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.deps.auth import require_user_id
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
    app.dependency_overrides[require_user_id] = lambda: "user-test-123"
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
