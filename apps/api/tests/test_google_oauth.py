"""Tests — OAuth state y normalización user_id."""

from __future__ import annotations

from unittest.mock import patch

from app.services.google_oauth import build_oauth_state, parse_oauth_state, store_tokens

SAMPLE_UUID = "550e8400-e29b-41d4-a716-446655440000"
SAMPLE_UUID_UPPER = "550E8400-E29B-41D4-A716-446655440000"


def test_normalize_user_id_lowercase():
    from app.services.user_id_utils import normalize_user_id

    assert normalize_user_id(SAMPLE_UUID_UPPER) == SAMPLE_UUID


def test_oauth_state_roundtrip():
    with patch("app.services.google_oauth._oauth_state_secret", return_value="test-secret-key-123456"):
        state = build_oauth_state(SAMPLE_UUID)
        uid, web = parse_oauth_state(state)
        assert uid == SAMPLE_UUID
        assert web is None


def test_oauth_state_with_web_origin():
    with patch("app.services.google_oauth._oauth_state_secret", return_value="test-secret-key-123456"):
        with patch(
            "app.services.google_oauth.get_settings",
        ) as mock_settings:
            mock_settings.return_value.cors_origin_list.return_value = [
                "https://app.example.com"
            ]
            state = build_oauth_state(SAMPLE_UUID, "https://app.example.com")
            uid, web = parse_oauth_state(state)
            assert uid == SAMPLE_UUID
            assert web == "https://app.example.com"


def test_oauth_state_legacy_uuid():
    uid, web = parse_oauth_state(SAMPLE_UUID_UPPER)
    assert uid == SAMPLE_UUID
    assert web is None


def test_store_tokens_normalizes_user_id():
    with patch("app.services.google_oauth.ensure_profile_for_oauth"):
        with patch("app.services.supabase_client.save_calendar_tokens"):
            with patch(
                "app.services.google_oauth.get_connection_status",
                return_value={"connected": True, "service": "calendar"},
            ):
                store_tokens(
                    "calendar",
                    SAMPLE_UUID_UPPER,
                    {"access_token": "tok", "refresh_token": "ref", "expires_in": 3600},
                )


def test_save_google_token_endpoint():
    from fastapi.testclient import TestClient

    from app.deps.auth import require_user_id
    from app.main import create_app

    app = create_app()
    app.dependency_overrides[require_user_id] = lambda: SAMPLE_UUID

    with patch("app.routers.google_auth.token_has_calendar_scope", return_value=True):
        with patch("app.routers.google_auth.store_tokens") as mock_store:
            with patch(
                "app.routers.google_auth.get_connection_status",
                return_value={"connected": True, "service": "calendar"},
            ):
                client = TestClient(app)
                res = client.post(
                    "/v1/google/save-token",
                    json={
                        "type": "calendar",
                        "provider_token": "ya29.provider-token",
                        "provider_refresh_token": "1//refresh",
                    },
                    headers={"Authorization": "Bearer test"},
                )
                assert res.status_code == 200
                assert res.json()["connected"] is True
                mock_store.assert_called_once()

    app.dependency_overrides.clear()
