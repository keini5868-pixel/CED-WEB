"""Tests — chat avanzado Claude."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.deps.auth import require_user_id
from app.main import create_app

SAMPLE_UUID = "550e8400-e29b-41d4-a716-446655440000"


def test_advanced_chat_endpoint():
    app = create_app()
    app.dependency_overrides[require_user_id] = lambda: SAMPLE_UUID

    def fake_send(user_id, *, message, history, conversation_id=None):
        return {
            "response": f"Análisis de: {message}",
            "model": "claude-sonnet-4-6",
        }

    with patch("app.routers.advanced_chat.send_advanced_message", fake_send):
        client = TestClient(app)
        res = client.post(
            "/v1/advanced/chat",
            json={"message": "estrategia de ventas", "history": []},
            headers={"Authorization": "Bearer test"},
        )

    assert res.status_code == 200
    body = res.json()
    assert "estrategia" in body["response"]
    assert body["model"] == "claude-sonnet-4-6"

    app.dependency_overrides.clear()


def test_advanced_status_missing_key():
    with patch("app.config.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(
            anthropic_api_key="",
            google_api_key="",
        )
        from app.config import get_settings

        get_settings.cache_clear()
        app = create_app()
        app.dependency_overrides[require_user_id] = lambda: SAMPLE_UUID
        client = TestClient(app)
        res = client.get(
            "/v1/advanced/status",
            headers={"Authorization": "Bearer test"},
        )

    assert res.status_code == 200
    assert res.json()["configured"] is False
    app.dependency_overrides.clear()


def test_advanced_status_google_only():
    with patch("app.config.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(
            anthropic_api_key="",
            google_api_key="gk-test",
        )
        from app.config import get_settings

        get_settings.cache_clear()
        app = create_app()
        app.dependency_overrides[require_user_id] = lambda: SAMPLE_UUID
        client = TestClient(app)
        res = client.get(
            "/v1/advanced/status",
            headers={"Authorization": "Bearer test"},
        )

    assert res.status_code == 200
    body = res.json()
    assert body["configured"] is True
    assert body["google_configured"] is True
    app.dependency_overrides.clear()
