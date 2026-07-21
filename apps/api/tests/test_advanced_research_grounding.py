"""Advanced mode must ground research queries (no ungrounded Claude stream)."""

from app.services.advanced_mode.intents import needs_advanced_full_pipeline


def test_investiga_without_internet_uses_full_pipeline():
    assert needs_advanced_full_pipeline("investiga quién ganó el mundial 2022", []) is True


def test_casual_chat_skips_full_pipeline():
    assert needs_advanced_full_pipeline("hola, cómo estás", []) is False


def test_explicit_web_search_still_uses_pipeline():
    assert needs_advanced_full_pipeline("busca en internet noticias de hoy", []) is True
