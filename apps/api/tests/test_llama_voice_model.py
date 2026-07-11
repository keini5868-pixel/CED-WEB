"""Tests — modelo de voz 3B y timeouts sincronizados."""

from __future__ import annotations

from app.services.llama_voice_llm import LLAMA_VOICE_TIMEOUT_SEC


def test_voice_timeout_above_http_chat_timeout() -> None:
    from app.services.llama_service import _CHAT_TIMEOUT_SEC, _VOICE_CHAT_TIMEOUT_SEC

    assert LLAMA_VOICE_TIMEOUT_SEC >= 24.0
    assert LLAMA_VOICE_TIMEOUT_SEC > _CHAT_TIMEOUT_SEC
    assert LLAMA_VOICE_TIMEOUT_SEC > _VOICE_CHAT_TIMEOUT_SEC


def test_llama_voice_model_default() -> None:
    from app.services.llama_service import llama_voice_model

    assert "3b" in llama_voice_model().lower() or "3.2" in llama_voice_model()


def test_call_llama_voice_chat_uses_voice_model(monkeypatch) -> None:
    from app.services import llama_service as ls

    captured: dict = {}

    def fake_chat(**kwargs):  # noqa: ANN003
        captured.update(kwargs)
        return "ok"

    monkeypatch.setattr(ls, "llama_voice_model_ready", lambda **k: True)
    monkeypatch.setattr(ls, "call_llama_chat", fake_chat)
    out = ls.call_llama_voice_chat(
        system="s",
        messages=[{"role": "user", "content": "hola"}],
    )
    assert out == "ok"
    assert captured.get("model") == ls.llama_voice_model()
    assert captured.get("timeout_sec") == ls._VOICE_CHAT_TIMEOUT_SEC
