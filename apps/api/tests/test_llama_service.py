"""Tests para llama_service — mocks HTTP, sin Ollama real."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.config import get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_use_llama_when_provider_llama(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "llama")
    get_settings.cache_clear()
    from app.services.llama_service import use_llama

    assert use_llama() is True


def test_use_llama_false_when_gemini(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    get_settings.cache_clear()
    from app.services.llama_service import use_llama

    assert use_llama() is False


def test_call_llama_local_parses_response(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "llama")
    monkeypatch.setenv("LLAMA_MODEL", "llama2:13b")
    get_settings.cache_clear()

    mock_response = MagicMock()
    mock_response.json.return_value = {"response": "Hola, señor."}
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post.return_value = mock_response

    with patch("app.services.llama_service.httpx.Client", return_value=mock_client):
        with patch("app.services.llama_service.llama_model_ready", return_value=True):
            from app.services.llama_service import call_llama_local

            text = call_llama_local("¿Cómo estás?", context="Contexto previo")
    assert text == "Hola, señor."
    payload = mock_client.post.call_args[1]["json"]
    assert payload["model"] == "llama2:13b"
    assert "Contexto previo" in payload["prompt"]


def test_call_llama_chat_parses_message(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "llama")
    get_settings.cache_clear()

    mock_response = MagicMock()
    mock_response.json.return_value = {"message": {"content": "Respuesta chat"}}
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post.return_value = mock_response

    with patch("app.services.llama_service.httpx.Client", return_value=mock_client):
        with patch("app.services.llama_service.llama_model_ready", return_value=True):
            from app.services.llama_service import call_llama_chat

            text = call_llama_chat(
                system="Eres CED",
                messages=[{"role": "user", "content": "Hola"}],
            )
    assert text == "Respuesta chat"


def test_llama_available_requires_model_ready(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "llama")
    get_settings.cache_clear()

    with patch(
        "app.services.llama_service.llama_model_ready",
        return_value=False,
    ):
        from app.services.llama_service import llama_available

        assert llama_available() is False


def test_should_route_false_without_model(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "llama")
    get_settings.cache_clear()

    with patch("app.services.llama_service.llama_model_ready", return_value=False):
        from app.services.llama_service import should_route_to_llama

        assert should_route_to_llama() is False


def test_llama_health_diagnostics_reports_error(monkeypatch):
    monkeypatch.setenv("LLAMA_ENDPOINT", "http://ced-llama.railway.internal:11434")
    get_settings.cache_clear()

    with patch("app.services.llama_service.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = TimeoutError("timed out")
        mock_client_cls.return_value = mock_client

        from app.services.llama_service import llama_health_diagnostics

        diag = llama_health_diagnostics()
    assert diag["ok"] is False
    assert "timed out" in str(diag.get("error", ""))
    assert diag["url"] == "http://ced-llama.railway.internal:11434/api/tags"
