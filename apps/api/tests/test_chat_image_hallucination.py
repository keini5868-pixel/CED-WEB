"""Tests — alucinación generate_image(...) y salvamento de generación directa."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.chat_image_generation import (
    _format_error,
    extract_hallucinated_generate_image_prompt,
    looks_like_hallucinated_generate_image,
    reply_promises_image_without_attachment,
    run_chat_image_generation,
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


def test_reply_dumps_prompt_instead_of_image_triggers_salvage_signal():
    from app.services.chat_image_generation import reply_dumps_prompt_instead_of_image

    user = "genera una imagen de un atardecer fotorrealista en la playa con palmeras"
    reply = (
        "Atardecer fotorrealista en la playa con palmeras, cielo naranja, "
        "arena dorada, composición horizontal."
    )
    assert reply_dumps_prompt_instead_of_image(reply, user)


def test_nano_banana_2_is_primary_image_model():
    from app.services.gemini_images import DEFAULT_GEMINI_IMAGE_MODELS, _image_models

    assert DEFAULT_GEMINI_IMAGE_MODELS[0] == "gemini-3.1-flash-image"
    with patch("app.services.gemini_images.get_settings") as mock_settings:
        mock_settings.return_value.gemini_image_model = "gemini-3.1-flash-image"
        models = _image_models()
    assert models[0] == "gemini-3.1-flash-image"
    assert "gemini-2.5-flash-image" in models


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


def test_format_error_is_honest_about_content_block_not_vagueness():
    """Regresión: cuando Gemini bloquea el pedido en silencio (personajes/marcas con
    copyright — Iron Man, Spider-Man, etc.), el mensaje no debía sugerir "sea más
    concreto" (engañoso — el problema no es vaguedad) ni, peor, dejar que capas
    superiores narren un falso éxito. Debe decir explícitamente que NO se generó
    ninguna imagen y ofrecer una alternativa sin la marca protegida.
    """
    raw = (
        "Gemini (gemini-2.5-flash-image) no devolvió imagen usable Intente un pedido "
        "más concreto, por ejemplo: 'genera una imagen de un atardecer en la playa "
        "con estilo fotorrealista'."
    )
    out = _format_error(raw)
    low = out.lower()
    assert "no pude generar la imagen" in low
    assert "no se generó ninguna imagen" in low
    assert "derechos de autor" in low
    assert "sea más concreto" not in low
    assert "pedido más concreto" not in low


@patch("app.services.gemini_images.generate_image")
def test_run_chat_image_generation_reports_content_block_honestly(mock_generate: MagicMock):
    mock_generate.return_value = {
        "ok": False,
        "error": (
            "Gemini (gemini-2.5-flash-image) no devolvió imagen usable Intente un "
            "pedido más concreto, por ejemplo: algo distinto."
        ),
        "code": "gemini_error",
    }
    result = run_chat_image_generation(
        "user-1",
        "conv-1",
        "genérame una imagen de la armadura de Iron Man",
        [],
        plan_id=None,
    )
    assert result["ok"] is False
    assert result.get("url") is None
    low = result["error"].lower()
    assert "derechos de autor" in low
    assert "no se generó ninguna imagen" in low
