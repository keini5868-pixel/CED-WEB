"""Tests — Gemini voz post-interrupción: web, truncamiento y fallback."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.gemini_voice_llm import (
    GeminiVoiceLlm,
    WEB_SEARCH_FALLBACK_OVERLAY,
    _looks_incomplete_voice_reply,
    _response_hit_max_tokens,
)
from app.services.voice_llm_common import WEB_SEARCH_VOICE_FALLBACK, voice_generation_limits


def test_news_query_gets_web_token_budget():
    text = "dime las últimas noticias de Donald Trump"
    max_tokens, timeout = voice_generation_limits(text)
    assert max_tokens >= 1536
    assert timeout >= 22.0


def test_default_voice_budget_above_legacy_640():
    max_tokens, timeout = voice_generation_limits("explícame embudos de venta brevemente")
    assert max_tokens >= 896
    assert timeout >= 16.0


def test_looks_incomplete_voice_reply_detects_mid_sentence():
    assert _looks_incomplete_voice_reply("medición detallada de")
    assert _looks_incomplete_voice_reply("clientes a través de plataformas como redes sociales...")
    assert not _looks_incomplete_voice_reply("Esto es una frase completa.")


def test_response_hit_max_tokens():
    response = MagicMock()
    response.candidates = [MagicMock(finish_reason="MAX_TOKENS")]
    assert _response_hit_max_tokens(response)


def test_build_draft_system_consumes_web_fallback_flag():
    llm = GeminiVoiceLlm.__new__(GeminiVoiceLlm)
    llm._web_search_fallback = True
    llm.user_id = "user-1"
    with patch("app.services.gemini_voice_llm.build_voice_system", return_value="BASE"):
        system = llm._build_draft_system("noticias de hoy")
    assert WEB_SEARCH_FALLBACK_OVERLAY in system
    assert llm._web_search_fallback is False


def test_ensure_complete_voice_reply_appends_continuation():
    async def run():
        llm = GeminiVoiceLlm.__new__(GeminiVoiceLlm)
        llm._raw_natural_reply = AsyncMock(return_value="resultados recientes del mercado.")
        response = MagicMock()
        response.candidates = [MagicMock(finish_reason="MAX_TOKENS")]
        contents = []
        result = await llm._ensure_complete_voice_reply(
            "medición detallada de",
            response=response,
            contents=contents,
            user_text="marketing digital",
            max_tokens=896,
            timeout_sec=16.0,
            path="draft_main",
        )
        assert result.endswith(".")
        assert "medición detallada de" in result
        assert "resultados recientes" in result

    asyncio.run(run())


def test_web_search_voice_fallback_phrase():
    assert "no pude obtener información actual" in WEB_SEARCH_VOICE_FALLBACK.lower()
    assert "registrado" in WEB_SEARCH_VOICE_FALLBACK.lower()


def test_search_web_tool_payload_timeout_uses_voice_fallback():
    spoken, payload = GeminiVoiceLlm._search_web_tool_payload(
        {"status": "timeout", "fallback": True, "spoken": ""},
    )
    assert payload.get("fallback") is True
    assert "no pude obtener información actual" in spoken.lower()


def test_search_web_tool_payload_success():
    spoken, payload = GeminiVoiceLlm._search_web_tool_payload(
        {"status": "success", "summary": "Noticia reciente sobre economía."},
    )
    assert payload.get("status") == "success"
    assert "Noticia reciente" in spoken


def test_ensure_complete_voice_reply_fits_without_regen():
    async def run():
        llm = GeminiVoiceLlm.__new__(GeminiVoiceLlm)
        llm._raw_natural_reply = AsyncMock()
        response = MagicMock()
        response.candidates = [MagicMock(finish_reason="STOP")]
        result = await llm._ensure_complete_voice_reply(
            "Respuesta corta y completa.",
            response=response,
            contents=[],
            user_text="hola",
            max_tokens=896,
            timeout_sec=16.0,
            path="draft_main",
        )
        assert result == "Respuesta corta y completa."
        llm._raw_natural_reply.assert_not_called()

    asyncio.run(run())
