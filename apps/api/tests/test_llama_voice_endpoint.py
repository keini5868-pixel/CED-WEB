"""Tests — endpoints Ollama separados texto/voz."""

from __future__ import annotations

import pytest

from app.config import get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_ollama_voice_base_falls_back_to_text_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLAMA_ENDPOINT", "http://ced-llama.railway.internal:11434")
    monkeypatch.delenv("LLAMA_VOICE_ENDPOINT", raising=False)
    get_settings.cache_clear()

    from app.services.llama_service import _ollama_voice_base, llama_voice_endpoint_separate

    assert _ollama_voice_base() == "http://ced-llama.railway.internal:11434"
    assert llama_voice_endpoint_separate() is False


def test_ollama_voice_base_uses_dedicated_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLAMA_ENDPOINT", "http://ced-llama.railway.internal:11434")
    monkeypatch.setenv("LLAMA_VOICE_ENDPOINT", "http://ced-llama-voice.railway.internal:11434")
    get_settings.cache_clear()

    from app.services.llama_service import _ollama_voice_base, llama_voice_endpoint_separate

    assert _ollama_voice_base() == "http://ced-llama-voice.railway.internal:11434"
    assert llama_voice_endpoint_separate() is True


def test_voice_model_ready_probes_voice_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLAMA_VOICE_ENDPOINT", "http://voice-ollama:11434")
    monkeypatch.setenv("LLAMA_VOICE_MODEL", "llama3.2:3b")
    get_settings.cache_clear()

    seen: dict[str, str] = {}

    def _fake_ready(**kwargs: object) -> bool:  # noqa: ANN003
        seen["base"] = str(kwargs.get("base"))
        seen["model"] = str(kwargs.get("model_name"))
        return True

    from app.services import llama_service as ls

    monkeypatch.setattr(ls, "_llama_health_model_ready", _fake_ready)
    assert ls.llama_voice_model_ready() is True
    assert seen["base"] == "http://voice-ollama:11434"
    assert seen["model"] == "llama3.2:3b"
