"""Factory de voz Retell — routing Claude / OpenAI / Gemini / Llama."""

from __future__ import annotations

from app.config import get_settings
from app.services.voice_llm_factory import build_voice_llm


def test_build_voice_llm_claude_when_configured(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("RETELL_LLM_PROVIDER", "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("VOICE_TEST_MODE", "")
    get_settings.cache_clear()

    llm = build_voice_llm()
    from app.services.claude_voice_llm import ClaudeVoiceLlm

    assert isinstance(llm, ClaudeVoiceLlm)


def test_build_voice_llm_gemini_when_explicit(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("RETELL_LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GOOGLE_API_KEY", "g-test")
    monkeypatch.setenv("VOICE_TEST_MODE", "")
    get_settings.cache_clear()

    llm = build_voice_llm()
    from app.services.gemini_voice_llm import GeminiVoiceLlm

    assert isinstance(llm, GeminiVoiceLlm)
