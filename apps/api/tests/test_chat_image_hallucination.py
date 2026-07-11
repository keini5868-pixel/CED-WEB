"""Tests — alucinación generate_image(...) y salvamento de generación directa."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.chat_image_generation import (
    extract_hallucinated_generate_image_prompt,
    looks_like_hallucinated_generate_image,
    reply_promises_image_without_attachment,
    salvage_image_turn,
    should_take_direct_image_path,
    strip_hallucinated_generate_image_text,
)
from app.services.chat_intents import is_generate_image_intent
from app.services.text_chat import (
    _can_stream_chat_text,
    _has_hallucinated_tool,
    _has_hallucinated_tool_code,
    _salvage_image_if_needed,
    _tool_hallucination_kind,
)

HALLUCINATED = (
    'generate_image({"prompt": "A beautiful, majestic tree in a meadow", '
    '"size": "1024x1024"})\nAquí está tu árbol. 🌳'
)

DIRECT_PROMPTS = [
    "genera una imagen de un árbol",
    "Genera una imagen de un atardecer en la playa",
    "create an image of a tree",
    "generate an image of a sunset",
    "make a picture of a mountain",
    "draw an illustration of a cat",
    "hazme una foto de un perro",
    "genera un creativo de un café",
]


def test_english_image_intents_use_direct_path_not_stream():
    for prompt in DIRECT_PROMPTS:
        assert is_generate_image_intent(prompt), prompt
        assert should_take_direct_image_path(prompt, []), prompt
        assert not _can_stream_chat_text(prompt), prompt


def test_detects_json_style_generate_image_hallucination():
    assert looks_like_hallucinated_generate_image(HALLUCINATED)
    assert _has_hallucinated_tool_code(HALLUCINATED)
    assert _has_hallucinated_tool(HALLUCINATED)
    assert _tool_hallucination_kind(HALLUCINATED) == "generate_image"


def test_extract_and_strip_hallucinated_tool_text():
    prompt = extract_hallucinated_generate_image_prompt(HALLUCINATED)
    assert prompt and "tree" in prompt.lower()
    stripped = strip_hallucinated_generate_image_text(HALLUCINATED)
    assert "generate_image" not in stripped
    assert "Aquí está tu árbol" in stripped


def test_reply_promises_image_without_attachment():
    assert reply_promises_image_without_attachment("Aquí está tu árbol. 🌳")
    assert not reply_promises_image_without_attachment("El árbol es una planta.")


@patch("app.services.chat_image_generation.run_chat_image_generation")
def test_salvage_runs_real_generation_and_removes_raw_tool_text(mock_gen: MagicMock):
    mock_gen.return_value = {
        "ok": True,
        "url": "https://example.com/tree.png",
        "reply": "Listo. Aquí está tu imagen generada.",
        "caption": "Árbol",
        "quality": "standard",
    }
    reply, attachment = salvage_image_turn(
        "user-1",
        "conv-1",
        "genera una imagen de un árbol",
        [],
        HALLUCINATED,
        None,
    )
    assert attachment and attachment.get("url")
    assert "generate_image" not in reply
    mock_gen.assert_called_once()


@patch("app.services.chat_image_generation.run_chat_image_generation")
def test_salvage_returns_clear_error_without_false_success(mock_gen: MagicMock):
    mock_gen.return_value = {
        "ok": False,
        "error": "No pude generar la imagen: límite diario alcanzado",
        "reply": "No pude generar la imagen: límite diario alcanzado",
    }
    reply, attachment = salvage_image_turn(
        "user-1",
        "conv-1",
        "create an image of a tree",
        [],
        HALLUCINATED,
        None,
    )
    assert attachment is None
    assert "generate_image" not in reply
    assert "límite" in reply.lower() or "no pude generar" in reply.lower()


@patch("app.services.chat_image_generation.run_chat_image_generation")
def test_salvage_if_needed_wrapper(mock_gen: MagicMock):
    mock_gen.return_value = {
        "ok": True,
        "url": "/media/tree.png",
        "reply": "Listo.",
        "caption": "Tree",
    }
    reply, attachment = _salvage_image_if_needed(
        "user-1",
        "conv-1",
        "generate an image of a tree",
        [],
        HALLUCINATED,
        None,
    )
    assert attachment
    assert "generate_image" not in reply


@patch("app.services.chat_image_generation.run_chat_image_generation")
def test_salvage_variants_for_direct_prompts(mock_gen: MagicMock):
    mock_gen.return_value = {
        "ok": True,
        "url": "https://example.com/img.png",
        "reply": "Listo.",
        "caption": "img",
    }
    for prompt in DIRECT_PROMPTS:
        halluc = f'generate_image({{"prompt": "{prompt}"}})\nDone.'
        reply, attachment = salvage_image_turn(
            "user-1",
            "conv-1",
            prompt,
            [],
            halluc,
            None,
        )
        assert attachment and attachment.get("url"), prompt
        assert "generate_image" not in reply, prompt
