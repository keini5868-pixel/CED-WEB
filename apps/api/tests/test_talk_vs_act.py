"""Conversar es el default. Imagen/PDF solo con mandato o oferta «¿la genero?»."""

from __future__ import annotations

from app.services.chat_image_generation import (
    should_generate_image_from_voice_turn,
    should_take_direct_image_path,
)
from app.services.chat_intents import (
    assistant_offered_image_act,
    is_exploratory_talk,
    is_explicit_image_command,
    is_generate_image_intent,
)
from app.services.marketing_creative import is_image_creation_request


_IDEA_TALK = [
    "tengo una idea para un flyer de Instagram",
    "vamos a hablar de una idea de campaña",
    "estaba pensando un creativo para el feed",
    "se me ocurrió algo para un post de venta",
    "quiero contarte una idea de negocio con FitLine",
    "tengo una idea",
]


def test_talking_about_an_idea_does_not_generate_image():
    for msg in _IDEA_TALK:
        assert is_exploratory_talk(msg) is True, msg
        assert is_generate_image_intent(msg) is False, msg
        assert should_take_direct_image_path(msg, []) is False, msg
        assert is_image_creation_request(msg, []) is False, msg


def test_explicit_generate_still_renders():
    msg = "genera una imagen de un atardecer"
    assert is_explicit_image_command(msg) is True
    assert is_exploratory_talk(msg) is False
    assert is_generate_image_intent(msg) is True
    assert should_take_direct_image_path(msg, []) is True


def test_generate_with_that_idea_is_an_act():
    msg = "Ok genérame una imagen con esa idea"
    assert is_generate_image_intent(msg) is True
    assert should_take_direct_image_path(msg, []) is True


def test_yes_without_offer_does_not_render():
    history = [
        {"role": "user", "content": "tengo una idea de flyer para Instagram"},
        {
            "role": "assistant",
            "content": "Buena idea. El gancho puede ser el resultado en 15 días.",
        },
    ]
    assert assistant_offered_image_act(history) is False
    assert should_take_direct_image_path("sí", history) is False
    assert should_take_direct_image_path("Ok. Te sigo. Que sea la primera.", history) is False
    assert should_generate_image_from_voice_turn("sí", "", history) is False


def test_yes_after_generate_offer_renders():
    history = [
        {"role": "user", "content": "un flyer de Restorate"},
        {
            "role": "assistant",
            "content": "Te propongo fondo oscuro y el logo. La genero ahora?",
        },
    ]
    assert assistant_offered_image_act(history) is True
    assert should_take_direct_image_path("sí", history) is True
    assert should_take_direct_image_path("dale", history) is True


def test_idea_talk_is_not_a_casual_interrupt_or_voice_module():
    from app.services.ced_orchestrator import detect_module
    from app.services.chat_intents import is_casual_chat_interrupt
    from app.services.voice_intent_gate import has_explicit_module_signal

    msg = "tengo una idea para un flyer de Instagram"
    assert is_casual_chat_interrupt(msg) is False
    assert has_explicit_module_signal(msg) is False
    assert detect_module(msg, []) is None


def test_fitline_restorate_is_not_a_topic_hijack():
    from app.services.chat_intents import is_casual_chat_interrupt

    assert is_casual_chat_interrupt("explícame Restorate y sus beneficios") is False
    assert is_casual_chat_interrupt("dame una idea de flyer de Restorate") is False
