"""OAuth Meta: state firmado, no user_id crudo."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.meta_oauth_state import sign_meta_oauth_state, verify_meta_oauth_state


@pytest.fixture
def oauth_secret(monkeypatch: pytest.MonkeyPatch):
    settings = MagicMock()
    settings.meta_app_secret.strip.return_value = "test-meta-secret"
    settings.supabase_jwt_secret.strip.return_value = ""
    monkeypatch.setattr("app.services.meta_oauth_state.get_settings", lambda: settings)
    return settings


def test_roundtrip_signed_state(oauth_secret) -> None:
    uid = "11111111-2222-3333-4444-555555555555"
    token = sign_meta_oauth_state(uid)
    assert token != uid
    assert verify_meta_oauth_state(token) == uid


def test_rejects_raw_user_id(oauth_secret) -> None:
    assert verify_meta_oauth_state("11111111-2222-3333-4444-555555555555") is None


def test_rejects_tampered_state(oauth_secret) -> None:
    uid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    token = sign_meta_oauth_state(uid)
    tampered = token[:-4] + "dead"
    assert verify_meta_oauth_state(tampered) is None


def test_rejects_expired_state(oauth_secret) -> None:
    uid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    token = sign_meta_oauth_state(uid)
    assert verify_meta_oauth_state(token, max_age_sec=-1) is None
