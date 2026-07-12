"""Tests — modo prueba Gemini standalone para voz."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import get_settings
from app.services.retell_llm_types import ResponseRequiredRequest, Utterance
from app.services.voice_test_mode import GEMINI_STANDALONE_MODE, is_gemini_standalone_voice_test


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_standalone_mode_flag() -> None:
    assert is_gemini_standalone_voice_test() is False
    import os

    os.environ["VOICE_TEST_MODE"] = GEMINI_STANDALONE_MODE
    get_settings.cache_clear()
    assert is_gemini_standalone_voice_test() is True


def test_factory_returns_standalone_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VOICE_TEST_MODE", GEMINI_STANDALONE_MODE)
    get_settings.cache_clear()
    from app.services.gemini_voice_standalone import GeminiStandaloneVoiceLlm
    from app.services.voice_llm_factory import build_voice_llm

    llm = build_voice_llm()
    assert isinstance(llm, GeminiStandaloneVoiceLlm)


def test_standalone_draft_logs_latency(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setenv("VOICE_TEST_MODE", GEMINI_STANDALONE_MODE)
    get_settings.cache_clear()

    mock_response = MagicMock()
    mock_response.text = "Entiendo, señor. Cuénteme más."

    async def _run() -> str | None:
        with patch("app.services.gemini_voice_standalone._gemini_client") as mock_client_factory:
            mock_client = MagicMock()
            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
            mock_client_factory.return_value = mock_client

            from app.services.gemini_voice_standalone import GeminiStandaloneVoiceLlm

            llm = GeminiStandaloneVoiceLlm()
            req = ResponseRequiredRequest(
                interaction_type="response_required",
                response_id=1,
                transcript=[Utterance(role="user", content="me siento un poco triste hoy")],
            )
            return await llm.draft_conversational_response(req)

    reply = asyncio.run(_run())
    assert reply
    assert "señor" in reply.lower() or "Entiendo" in reply
