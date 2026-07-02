"""Tests — intención web Trump/noticias y timeout fast-path."""

from __future__ import annotations

from app.routers.retell_custom_llm import WEB_SEARCH_FAST_PATH_TIMEOUT_SEC
from app.services.retell_custom_llm import resolve_web_search_request
from app.services.retell_llm_types import Utterance
from app.services.voice_tool_executor import execute_voice_tool


def test_trump_news_resolves_web_search():
    text = "Dame las últimas noticias de Donald Trump"
    tx = [
        Utterance(role="agent", content="CED en línea, señor."),
        Utterance(role="user", content="¿Cómo estás?"),
        Utterance(role="agent", content="Muy bien, señor."),
        Utterance(role="user", content=text),
    ]
    req = resolve_web_search_request(text, tx)
    assert req is not None
    assert req["kind"] == "news"
    assert "trump" in req["query"].lower()


def test_web_search_fast_path_timeout_is_15s():
    assert WEB_SEARCH_FAST_PATH_TIMEOUT_SEC == 15.0


def test_english_concept_question_detected():
    from app.services.retell_custom_llm import _is_concept_question

    assert _is_concept_question("what is digital marketing")
    assert _is_concept_question("What is the digital market?")


def test_marketing_digital_routes_to_draft_not_web():
    from app.services.retell_custom_llm import should_respond_to_transcript

    text = "what is digital marketing"
    tx = [
        Utterance(role="agent", content="Señor, sobre su consulta: Trump news..."),
        Utterance(role="user", content=text),
    ]
    assert resolve_web_search_request(text, tx) is None
    assert should_respond_to_transcript(tx, interaction_type="response_required") is True


def test_research_question_uses_live_web_not_internal_kb():
    import asyncio
    from unittest.mock import patch

    query = "han investigado esta teoria de terremotos y energias humanas"
    internal_called = {"v": False}
    web_called = {"v": False}

    async def fake_internal(*_a, **_k):
        internal_called["v"] = True
        return [{"summary": "Keini Castillo es el creador"}]

    async def fake_brief(*_a, **_k):
        web_called["v"] = True
        return {
            "ok": True,
            "summary": "Existen estudios sobre geoenergía y sismicidad, señor.",
            "source": "tavily",
        }

    with patch("app.services.voice_tool_executor.search_internal_knowledge", fake_internal):
        with patch("app.services.voice_tool_executor.fetch_voice_brief_parallel", fake_brief):
            result = asyncio.run(
                execute_voice_tool(
                    "search_web",
                    "user-test-123",
                    {"query": query, "kind": "general"},
                )
            )

    assert web_called["v"] is True
    assert internal_called["v"] is False
    assert result.get("status") == "success"
    assert "estudios" in str(result.get("spoken") or "").lower()
