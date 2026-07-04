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


def test_build_image_generation_prompts_generic_subject():
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
