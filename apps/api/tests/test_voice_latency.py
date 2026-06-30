"""Tests — optimizaciones de latencia voz/chat."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.domain.openai_voice_prompt import build_ced_voice_system_prompt, voice_prompt_diagnostics
from app.routers.retell_custom_llm import _debounce_wait_s
from app.services.kb_turn_cache import clear_turn_kb_cache, get_turn_kb_hits
from app.services.openai_voice_llm import OpenAIVoiceLlm, _api_key, _voice_model
from app.services.voice_llm_common import build_voice_system


def test_openai_voice_llm_imports_get_settings():
    """Regresión 6f15302: get_settings debe existir para instanciar el LLM."""
    assert _voice_model()
    with patch("app.services.openai_voice_llm.get_settings") as mock_settings:
        mock_settings.return_value.openai_api_key = "sk-test-key"
        assert _api_key() == "sk-test-key"
    llm = OpenAIVoiceLlm()
    assert llm.model


def test_debounce_wait_reduced_for_short_utterances():
    assert _debounce_wait_s("hola") == 0.15
    assert _debounce_wait_s("cómo estás hoy") == 0.15
    assert _debounce_wait_s(" ".join(["palabra"] * 12)) == 0.25
    assert _debounce_wait_s(" ".join(["palabra"] * 22)) == 0.30


def test_kb_turn_cache_dedupes_same_query():
    clear_turn_kb_cache()
    calls = {"n": 0}

    def fake_search(query: str, *, limit: int = 2):
        calls["n"] += 1
        hit = MagicMock()
        hit.confidence = 0.9
        hit.title = "Test"
        hit.domain_label = "sales"
        hit.content = "Contenido de prueba interna."
        return [hit]

    with patch("app.services.internal_knowledge.search_internal_knowledge", side_effect=fake_search):
        first = get_turn_kb_hits("qué es prospección", limit=2)
        second = get_turn_kb_hits("qué es prospección", limit=2)

    assert len(first) == 1
    assert first is not second
    assert calls["n"] == 1


def test_conversational_build_voice_system_skips_kb():
    with patch("app.services.kb_turn_cache.get_turn_kb_hits") as mock_kb:
        system = build_voice_system("user-1", "hola cómo estás", skip_kb=True, lightweight=True)
        mock_kb.assert_not_called()
    assert "CED" in system


def test_voice_prompt_compressed_under_previous_size():
    diag = voice_prompt_diagnostics()
    assert diag["prompt_chars"] < 16000
    assert diag["prompt_chars"] < 16702
    prompt = build_ced_voice_system_prompt()
    assert "FUNCTION CALLING OBLIGATORIO" in prompt
    assert "SOLO BAJO COMANDO EXPLÍCITO" in prompt
    assert "publicar_facebook" in prompt
