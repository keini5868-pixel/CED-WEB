"""Tests de preparación genérica de prompts para generación de imágenes Gemini."""

from app.services.chat_intents import (
    is_generate_image_intent,
    parse_generate_image_prompt,
    parse_followup_image_prompt,
)
from app.services.gemini_images import (
    build_image_generation_prompts,
    prepare_image_prompt,
    strip_image_generation_instruction,
)
from app.services.text_chat import _format_image_generation_error


def test_generas_conjugation_matches_image_intent():
    msg = "me generas una imagen con el producto y sus expecificaciones y veneficios"
    assert is_generate_image_intent(msg)
    assert parse_generate_image_prompt(msg) == (
        "el producto y sus expecificaciones y veneficios"
    )


def test_strip_image_generation_instruction():
    assert strip_image_generation_instruction(
        "me generas una imagen con el producto y sus beneficios"
    ) == "el producto y sus beneficios"


def test_prepare_image_prompt_uses_conversation_for_specs():
    context = (
        "el basics de fitline es un producto. Fitline Basics es un complemento en polvo "
        "para sistema inmunológico, vitaminas C y E, selenio."
    )
    prepared = prepare_image_prompt(
        "el producto y sus expecificaciones y veneficios",
        context,
    )
    assert "Ortografía española" in prepared or "ortografía" in prepared.lower()
    assert "basics" in prepared.lower() or "fitline" in prepared.lower()
    assert "me generas una imagen" not in prepared.lower()
    assert "el producto y sus" not in prepared.lower()
    assert "Instrucciones actuales" not in prepared
    assert "según este pedido" not in prepared.lower()


def test_prepare_image_prompt_strips_meta_wrappers_that_leak_into_pixels():
    """Regression: wrappers internos no deben llegar al brief que ve Gemini Image."""
    leaked = (
        "Instrucciones actuales del usuario (obligatorias):\n"
        "Genera una imagen de alta calidad según este pedido: Goku en Super Saiyan."
    )
    prepared = prepare_image_prompt("genera una imagen de Goku en Super Saiyan", leaked)
    low = prepared.lower()
    assert "goku" in low
    assert "instrucciones actuales del usuario" not in low
    assert "según este pedido" not in low
    assert "genera una imagen de alta calidad" not in low


def test_build_image_generation_prompts_are_visual_only():
    variants = build_image_generation_prompts("Goku en Super Saiyan azul")
    joined = " ".join(variants).lower()
    assert "goku" in joined
    assert "genera una imagen de alta calidad según este pedido" not in joined
    assert "instrucciones actuales" not in joined


def test_generate_image_with_reference_gemini_imports_augment_prompt():
    from unittest.mock import MagicMock, patch

    from app.services.gemini_images import generate_image_with_reference_gemini

    fake_client = MagicMock()
    fake_response = MagicMock()
    fake_response.candidates = []
    fake_client.models.generate_content.return_value = fake_response

    with patch("app.services.gemini_images.get_settings") as mock_settings:
        mock_settings.return_value.google_api_key = "test-key"
        mock_settings.return_value.gemini_image_model = "gemini-2.0-flash-preview-image-generation"
        with patch("google.genai.Client", return_value=fake_client):
            result = generate_image_with_reference_gemini(
                prompt="creativo con beneficios del producto",
                reference_image=b"\xff\xd8\xff\xd9",
                content_type="image/jpeg",
                style_mode="edit",
            )
    assert result["ok"] is False
    assert "augment_image_prompt" not in str(result.get("error", ""))
    assert "not defined" not in str(result.get("error", "")).lower()

    variants = build_image_generation_prompts("un castillo digital futurista al atardecer")
    assert len(variants) == 3
    joined = " ".join(variants).lower()
    assert "castillo" in joined


def test_parse_followup_image_prompt_after_any_image_thread():
    history = [
        {"role": "user", "content": "genera una imagen de un castillo medieval"},
        {"role": "model", "content": "Listo. Aquí está tu imagen generada."},
    ]
    assert parse_followup_image_prompt("ahora con tormenta eléctrica", history) == (
        "ahora con tormenta eléctrica"
    )
    assert parse_followup_image_prompt("ok gracias", history) is None


def test_parse_followup_image_prompt_does_not_hijack_casual_chat_after_image():
    """Regresión: tras generar una imagen, cualquier mensaje casual sin señal real de
    edición NO debe interpretarse como continuación del hilo visual (bug reportado:
    chat normal generaba imagen con cualquier mensaje tras el primer pedido)."""
    from app.services.chat_image_generation import should_take_direct_image_path

    history = [
        {"role": "user", "content": "genera una imagen de un atardecer en la playa"},
        {"role": "assistant", "content": "Listo. Aquí está tu imagen generada."},
    ]
    casual_messages = [
        "¿cómo estás?",
        "cuéntame sobre el sistema solar",
        "qué opinas de la economía actual",
        "tengo una duda sobre mi negocio",
        "quiero hablar de otra cosa",
        "cuánto es 2 más 2",
        "qué hora es en España",
        "me puedes explicar qué es la inflación",
    ]
    for msg in casual_messages:
        assert parse_followup_image_prompt(msg, history) is None, msg
        assert should_take_direct_image_path(msg, history) is False, msg

    # Pero un seguimiento real de edición sigue funcionando.
    assert parse_followup_image_prompt("hazla más grande", history) == "hazla más grande"
    assert should_take_direct_image_path("hazla más grande", history) is True
    # Y un pedido explícito de imagen nueva sigue disparando normalmente.
    assert should_take_direct_image_path("genera una imagen de un gato", history) is True


def test_parse_followup_image_prompt_not_after_strategy_plan_only():
    """Plan estratégico menciona creativo/imagen pero no hubo generación real."""
    history = [
        {
            "role": "user",
            "content": "me das esta info en un pdf ### Plan Semanal ... creativo para anuncio ...",
        },
        {
            "role": "assistant",
            "content": 'Listo. PDF "Plan Semanal de Estrategia CED" generado. Usa el botón Descargar.',
        },
    ]
    msg = "sabes hoy estoy con un dolor de cabeza cambiando el tema"
    assert parse_followup_image_prompt(msg, history) is None


def test_casual_chat_interrupt_blocks_followup_even_with_image_thread():
    history = [
        {"role": "user", "content": "genera una imagen de un castillo medieval"},
        {"role": "model", "content": "Listo. Aquí está tu imagen generada."},
    ]
    assert (
        parse_followup_image_prompt("cambiando el tema, hoy estoy mal de cabeza", history)
        is None
    )


def test_prepare_image_prompt_resolves_esa_informacion():
    context = (
        "FitLine Basics: fibra, probióticos, vitaminas C y E. "
        "Beneficios: intestinal, inmunológico, antioxidante."
    )
    prepared = prepare_image_prompt(
        "esa informacion del los beneficios y productos",
        context,
    )
    assert "basics" in prepared.lower() or "fitline" in prepared.lower()
    assert "esa informacion" not in prepared.lower()


def test_format_image_generation_error_avoids_duplicate_prefix():
    assert _format_image_generation_error("Gemini no devolvió imagen usable").startswith(
        "No pude generar la imagen:"
    )
    assert (
        _format_image_generation_error("No pude generar la imagen: ya falló")
        == "No pude generar la imagen: ya falló"
    )
