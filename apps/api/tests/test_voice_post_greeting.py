"""Tests — silencio post-saludo: transcript Retell y anti-silencio."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from app.services.gemini_voice_llm import GeminiVoiceLlm
from app.services.kb_turn_cache import clear_turn_kb_cache, get_turn_kb_hits
from app.services.retell_custom_llm import looks_incomplete_user_utterance, should_respond_to_transcript
from app.services.retell_llm_types import ResponseRequiredRequest, Utterance


def test_hola_after_greeting_should_respond():
    tx = [
        Utterance(role="agent", content="CED en línea, señor."),
        Utterance(role="user", content="hola"),
    ]
    assert should_respond_to_transcript(tx, interaction_type="response_required") is True


def test_como_estas_after_greeting_should_respond():
    tx = [
        Utterance(role="agent", content="CED en línea, señor."),
        Utterance(role="user", content="¿Cómo estás?"),
    ]
    assert should_respond_to_transcript(tx, interaction_type="response_required") is True


def test_partial_stt_fragment_should_not_respond():
    tx = [
        Utterance(role="agent", content="CED en línea, señor."),
        Utterance(role="user", content="¿C"),
    ]
    assert should_respond_to_transcript(tx, interaction_type="response_required") is False


def test_mid_sentence_pause_should_not_respond():
    assert looks_incomplete_user_utterance("necesito que") is True
    assert looks_incomplete_user_utterance("oye ced") is True
    assert looks_incomplete_user_utterance("genera un") is True
    assert looks_incomplete_user_utterance("ayúdame con") is True
    assert looks_incomplete_user_utterance("hola") is False
    assert looks_incomplete_user_utterance("¿Cómo estás?") is False
    assert looks_incomplete_user_utterance("necesito que me hagas un pdf") is False

    tx = [
        Utterance(role="agent", content="CED en línea, señor."),
        Utterance(role="user", content="oye necesito que me generes"),
    ]
    assert should_respond_to_transcript(tx, interaction_type="response_required") is False

    done = [
        Utterance(role="agent", content="CED en línea, señor."),
        Utterance(role="user", content="necesito que me hagas un pdf del presupuesto"),
    ]
    assert should_respond_to_transcript(done, interaction_type="response_required") is True


def test_draft_response_yields_when_agent_is_last_in_transcript():
    """Retell a veces envía el saludo del agente como último turno del transcript."""
    with patch("app.services.gemini_voice_llm.get_settings") as mock_settings:
        mock_settings.return_value.google_api_key = "test-key"
        mock_settings.return_value.gemini_voice_model = "gemini-2.5-flash"
        with patch("app.services.gemini_voice_llm._gemini_client") as mock_client:
            mock_client.return_value = MagicMock()
            llm = GeminiVoiceLlm()

    request = ResponseRequiredRequest(
        interaction_type="response_required",
        response_id=3,
        transcript=[
            Utterance(role="user", content="¿qué es el marketing digital?"),
            Utterance(role="agent", content="De regreso, señor. ¿Continuamos?"),
        ],
    )

    async def fake_generate(**kwargs: object) -> MagicMock:
        response = MagicMock()
        response.text = (
            "Señor, el marketing digital es promocionar negocios "
            "en internet con redes, contenido y publicidad online."
        )
        response.candidates = []
        return response

    async def run() -> list[str]:
        with patch.object(llm, "_generate_with_timeout", side_effect=fake_generate):
            with patch.object(
                llm,
                "_sanitize_voice_output",
                side_effect=lambda text, **_: text,
            ):
                events = [event async for event in llm.draft_response(request)]
        return [ev.content for ev in events]

    contents = asyncio.run(run())
    assert len(contents) == 1
    assert "marketing digital" in contents[0].lower()


def test_kb_turn_cache_survives_search_errors():
    clear_turn_kb_cache()
    with patch(
        "app.services.internal_knowledge.search_internal_knowledge",
        side_effect=RuntimeError("db down"),
    ):
        hits = get_turn_kb_hits("qué es marketing digital", limit=2)
    assert hits == []
