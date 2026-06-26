"""Tests — parámetros Tavily optimizados."""

from app.services.tavily_search import (
    DEFAULT_MAX_RESULTS,
    infer_tavily_topic,
    resolve_search_depth,
)


def test_tavily_default_max_results_is_three():
    assert DEFAULT_MAX_RESULTS == 3


def test_infer_tavily_topic_news_kind():
    assert infer_tavily_topic("clima en Charlotte", kind="news") == "news"


def test_infer_tavily_topic_general_default():
    assert infer_tavily_topic("Cristiano Ronaldo", kind="general") == "general"


def test_infer_tavily_topic_news_from_query_hints():
    assert infer_tavily_topic("noticias de Venezuela hoy", kind="general") == "news"


def test_resolve_search_depth_basic_by_default():
    assert resolve_search_depth("clima en Charlotte hoy") == "basic"


def test_resolve_search_depth_advanced_for_research():
    assert resolve_search_depth("investigación profunda sobre IA", research=True) == "advanced"
    assert resolve_search_depth("modo avanzado análisis mercado") == "advanced"
