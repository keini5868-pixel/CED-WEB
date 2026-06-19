"""Tests — detección web Retell (sin mezclar noticias previas)."""

from app.services.retell_custom_llm import resolve_web_search_request
from app.services.retell_llm_types import Utterance


def _tx(*lines: tuple[str, str]) -> list[Utterance]:
    return [Utterance(role=role, content=text) for role, text in lines]


def test_news_only_last_turn():
    tx = _tx(
        ("user", "Sí, dime las noticias del día de hoy en Estados Unidos."),
    )
    req = resolve_web_search_request(tx[-1].content, tx)
    assert req is not None
    assert req["kind"] == "news"
    assert "noticias" in req["query"].lower()


def test_creatine_not_news_after_news_turn():
    tx = _tx(
        ("user", "Sí, dime las noticias del día de hoy en Estados Unidos."),
        ("user", "Búscame en la web qué es la creatina."),
    )
    last = tx[-1].content
    req = resolve_web_search_request(last, tx)
    assert req is not None
    assert req["kind"] == "general"
    assert "creatina" in req["query"].lower()
    assert "noticias" not in req["query"].lower()


def test_fragment_country_completes_news():
    tx = _tx(
        ("user", "Dime las últimas noticias"),
        ("user", "de Estados Unidos."),
    )
    last = tx[-1].content
    req = resolve_web_search_request(last, tx)
    assert req is not None
    assert req["kind"] == "news"
    assert "Estados Unidos" in req["query"]


def test_ack_only_skipped():
    tx = _tx(("user", "Okay."),)
    assert resolve_web_search_request("Okay.", tx) is None
