"""Hilo visual estilo ChatGPT — ejemplos en texto, mismo diseño, render bajo demanda."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.chat_image_generation import (
    build_active_image_thread_context,
    should_take_direct_image_path,
    should_use_reference_generation,
)
from app.services.chat_intents import is_visual_design_exploration

BATHROOM_HISTORY = [
    {
        "role": "user",
        "content": (
            "Este espacio como se vería mejor con qué tipo de espejos y lámparas"
        ),
    },
    {
        "role": "assistant",
        "content": (
            "Aquí está la imagen editada con dos espejos arqueados y lámpara horizontal."
        ),
    },
    {
        "role": "user",
        "content": "Y si le ponemos un solo espejo largo con luz LED cómo se vería",
    },
    {
        "role": "assistant",
        "content": (
            "Un espejo largo con luz LED cambiaría la percepción del espacio. "
            "Vertical en toda la pared multiplica altura; luz fría vs cálida cambia el ambiente."
        ),
    },
]

USER = "user-vdt"
CONV = "conv-vdt"


FLYER_HISTORY = [
    {
        "role": "user",
        "content": "Genera un flyer de Restorate con precios $49 $79 $99 fondo oscuro",
    },
    {
        "role": "assistant",
        "content": "Listo. Aquí está tu imagen generada — flyer Restorate con precios.",
    },
]


def test_visual_exploration_does_not_trigger_image():
    msgs = [
        "dame 3 ejemplos de cómo cambiar esa imagen",
        "muéstrame opciones para ese diseño",
        "cómo se vería con fondo azul",
        "y si le ponemos marco dorado",
        "ejemplos para la misma imagen del baño",
    ]
    for msg in msgs:
        assert is_visual_design_exploration(msg, BATHROOM_HISTORY), msg
        assert should_take_direct_image_path(msg, BATHROOM_HISTORY) is False, msg


def test_visual_exploration_works_for_any_topic_not_just_bathroom():
    """El hilo visual es genérico: flyer, producto, logo — no solo baño/espejo."""
    msgs = [
        "dame ejemplos para ese flyer",
        "cómo se vería con tipografía más grande",
        "muéstrame opciones de color para ese diseño",
    ]
    for msg in msgs:
        assert is_visual_design_exploration(msg, FLYER_HISTORY), msg
        assert should_take_direct_image_path(msg, FLYER_HISTORY) is False, msg
    ctx = build_active_image_thread_context(FLYER_HISTORY)
    low = ctx.lower()
    assert "hilo visual activo" in low
    assert "restorate" in low or "flyer" in low or "$49" in low


def test_explicit_generate_still_triggers_after_thread():
    msg = "Genera una imagen de ese ejemplo para ver cómo se vería"
    assert is_visual_design_exploration(msg, BATHROOM_HISTORY) is False
    assert should_take_direct_image_path(msg, BATHROOM_HISTORY) is True


def test_build_thread_context_includes_bathroom_scene():
    ctx = build_active_image_thread_context(BATHROOM_HISTORY)
    low = ctx.lower()
    assert "hilo visual activo" in low
    assert "espejo" in low or "led" in low or "luz" in low
    assert "chatgpt" in low or "iteración" in low


def test_thread_context_empty_without_visual_thread():
    assert build_active_image_thread_context([]) == ""
    assert is_visual_design_exploration("dame ejemplos de marketing", []) is False


@patch("app.services.publish_image_context.resolve_reference_image_bytes")
def test_anaphoric_generate_uses_reference_in_thread(mock_resolve: MagicMock):
    png = b"\x89PNG\r\n\x1a\n"
    mock_resolve.return_value = (png, "image/png")

    msg = "Genera una imagen de ese ejemplo para ver cómo se vería"
    assert should_use_reference_generation(
        msg,
        BATHROOM_HISTORY,
        user_id=USER,
        conversation_id=CONV,
    )
