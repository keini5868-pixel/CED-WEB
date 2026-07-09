"""Tests — fallback cloud cuando Llama no está disponible."""

from __future__ import annotations

from unittest.mock import patch

from app.services.cloud_llm_fallback import chat_cloud_reply, cloud_llm_configured


def test_cloud_llm_configured_requires_keys():
    from app.config import get_settings

    get_settings.cache_clear()
    with patch("app.services.cloud_llm_fallback.get_settings") as mock_settings:
        mock_settings.return_value.google_api_key = ""
        mock_settings.return_value.anthropic_api_key = ""
        assert cloud_llm_configured() is False

    get_settings.cache_clear()
    with patch("app.services.cloud_llm_fallback.get_settings") as mock_settings:
        mock_settings.return_value.google_api_key = "gk-test"
        mock_settings.return_value.anthropic_api_key = ""
        assert cloud_llm_configured() is True


def test_chat_cloud_reply_skips_llama(monkeypatch):
    monkeypatch.setattr(
        "app.services.text_chat._gemini_simple_reply",
        lambda **kwargs: (
            "cloud-ok" if kwargs.get("allow_llama") is False else "llama-path"
        ),
    )
    with patch("app.config.get_settings") as mock_settings:
        mock_settings.return_value.google_api_key = "gk-test"
        mock_settings.return_value.anthropic_api_key = ""
        reply = chat_cloud_reply(
            system="sys",
            messages=[{"role": "user", "content": "hola"}],
        )
    assert reply == "cloud-ok"
