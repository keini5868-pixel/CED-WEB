"""Tests — silencio post-saludo: transcript Retell y anti-silencio."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from app.services.kb_turn_cache import clear_turn_kb_cache, get_turn_kb_hits
from app.services.openai_voice_llm import OpenAIVoiceLlm
from app.services.retell_llm_types import ResponseRequiredRequest, Utterance


def test_draft_response_yields_when_agent_is_last_in_transcript():
    """Retell a veces envía el saludo del agente como último turno del transcript."""
    llm = OpenAIVoiceLlm()
    request = ResponseRequiredRequest(
        interaction_type="response_required",
        response_id=3,
        transcript=[
            Utterance(role="user", content="¿qué es el marketing digital?"),
            Utterance(role="agent", content="De regreso, señor. ¿Continuamos?"),
        ],
    )

    async def fake_completion(**kwargs: object) -> dict:
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            "Señor, el marketing digital es promocionar negocios "
                            "en internet con redes, contenido y publicidad online."
                        )
                    }
                }
            ]
        }

    async def run() -> list[str]:
        with patch.object(llm, "_chat_completion", side_effect=fake_completion):
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
