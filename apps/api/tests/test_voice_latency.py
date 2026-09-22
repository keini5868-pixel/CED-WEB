"""Tests — optimizaciones de latencia voz/chat."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.domain.openai_voice_prompt import build_ced_voice_system_prompt, voice_prompt_diagnostics
from app.routers.retell_custom_llm import _debounce_wait_s
from app.services.retell_agent_setup import retell_turn_taking_payload
from app.services.gemini_voice_llm import GeminiVoiceLlm, _voice_model
from app.services.kb_turn_cache import clear_turn_kb_cache, get_turn_kb_hits
from app.services.voice_llm_common import build_voice_system


def test_gemini_voice_llm_imports_get_settings():
    """GeminiVoiceLlm debe instanciarse con GOOGLE_API_KEY configurada."""
    assert _voice_model()
    with patch("app.services.gemini_voice_llm.get_settings") as mock_settings:
        mock_settings.return_value.google_api_key = "test-google-key"
        mock_settings.return_value.gemini_voice_model = "gemini-2.5-flash"
        with patch("app.services.gemini_voice_llm._gemini_client") as mock_client:
            mock_client.return_value = MagicMock()
            llm = GeminiVoiceLlm()
            assert llm.model == "gemini-2.5-flash"


def test_retell_turn_taking_is_claude_like():
    payload = retell_turn_taking_payload()
    assert payload["enable_backchannel"] is False
    assert payload["interruption_sensitivity"] >= 0.85
    assert payload["responsiveness"] <= 0.55


def test_debounce_wait_reduced_for_short_utterances():
    assert _debounce_wait_s("hola") == 0.42
    assert _debounce_wait_s("cómo estás hoy") == 0.42
    assert _debounce_wait_s(" ".join(["palabra"] * 12)) == 0.48
    assert _debounce_wait_s(" ".join(["palabra"] * 22)) == 0.52
    assert _debounce_wait_s("necesito que") == 0.72


def test_kb_turn_cache_dedupes_same_query():
    clear_turn_kb_cache()
    calls = {"n": 0}

    def fake_search(query: str, *, limit: int = 2):
        calls["n"] += 1
        hit = MagicMock()
        hit.confidence = 0.9
        hit.title = "Test"
        hit.summary = "Resumen"
        hit.domain_id = "marketing"
        hit.domain_label = "Marketing"
        return [hit]

    with patch("app.services.internal_knowledge.search_internal_knowledge", side_effect=fake_search):
        q = "qué es marketing digital"
        get_turn_kb_hits(q, limit=2)
        get_turn_kb_hits(q, limit=2)
    assert calls["n"] == 1


def test_build_voice_system_skips_kb_when_lightweight():
    with patch("app.services.kb_turn_cache.get_turn_kb_hits") as mock_kb:
        system = build_voice_system("user-1", "hola cómo estás", skip_kb=True, lightweight=True)
        mock_kb.assert_not_called()
    assert "CED" in system


def test_voice_prompt_compressed_under_previous_size():
    diag = voice_prompt_diagnostics()
    assert diag["prompt_chars"] < 40000
    prompt = build_ced_voice_system_prompt()
    assert "FUNCTION CALLING OBLIGATORIO" in prompt
    assert "CONVERSACIÓN UNIVERSAL" in prompt
    assert "Gemini 2.5 Flash" in prompt
    assert "publicar_facebook" in prompt
    assert diag["includes_universal_conversation"] is True
    assert diag["llm_provider"] == "gemini_2.5_flash"
