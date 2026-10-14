"""Analizar / cómo se hace: Centinela bloquea generar imagen."""

from app.services.ced_sentinel import intercept_help_not_generate
from app.services.chat_intents import attachment_stays_on_vision, is_attachment_vision_question


def test_analyze_mode_wins_even_if_text_sounds_like_create():
    assert attachment_stays_on_vision("analyze", "hazme esto igual") is True
    assert attachment_stays_on_vision("analyze", "cómo se hace este plato") is True


def test_edit_mode_still_generates():
    assert attachment_stays_on_vision("edit", "cómo se hace") is False


def test_howto_question_without_mode():
    assert is_attachment_vision_question("cómo hago esa receta de la foto") is True
    assert intercept_help_not_generate("explícame cómo se prepara esto") is True


def test_explicit_flyer_is_not_help():
    assert intercept_help_not_generate("genera un flyer con fondo negro") is False
