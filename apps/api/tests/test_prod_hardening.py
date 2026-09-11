"""Diagnósticos de voz y webhooks no quedan abiertos en production."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import create_app
from app.routers.automation_pilot import _verify_meta_signature
from app.services.whatsapp_cloud import verify_webhook_signature


def test_llm_websocket_active_requires_auth() -> None:
    client = TestClient(create_app())
    res = client.get("/llm-websocket/active")
    assert res.status_code == 401


def test_whatsapp_signature_fail_closed_in_production() -> None:
    with patch("app.services.whatsapp_cloud.get_settings") as settings:
        settings.return_value.meta_app_secret.strip.return_value = ""
        settings.return_value.is_production.return_value = True
        assert verify_webhook_signature(b"{}", None) is False


def test_automation_signature_fail_closed_in_production() -> None:
    settings = MagicMock()
    settings.instagram_app_secret = ""
    settings.meta_app_secret = ""
    settings.is_production.return_value = True
    with patch("app.routers.automation_pilot.get_settings", return_value=settings):
        assert _verify_meta_signature(b"{}", None) is False
