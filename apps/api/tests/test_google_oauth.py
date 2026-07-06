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
        assert parse_oauth_state(state) == SAMPLE_UUID


def test_oauth_state_legacy_uuid():
    assert parse_oauth_state(SAMPLE_UUID_UPPER) == SAMPLE_UUID


def test_store_tokens_normalizes_user_id():
    with patch("app.services.google_oauth.ensure_profile_for_oauth"):
        with patch("app.services.supabase_client.save_calendar_tokens") as save:
            store_tokens(
                "calendar",
                SAMPLE_UUID_UPPER,
                {"access_token": "tok", "refresh_token": "ref", "expires_in": 3600},
            )
            save.assert_called_once()
            assert save.call_args[0][0] == SAMPLE_UUID
