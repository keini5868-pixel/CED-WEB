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
