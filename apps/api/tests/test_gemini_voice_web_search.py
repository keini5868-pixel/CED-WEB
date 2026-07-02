"""Tests — intención web Trump/noticias y timeout fast-path."""

from __future__ import annotations

from app.routers.retell_custom_llm import WEB_SEARCH_FAST_PATH_TIMEOUT_SEC
from app.services.retell_custom_llm import resolve_web_search_request
from app.services.retell_llm_types import Utterance


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
