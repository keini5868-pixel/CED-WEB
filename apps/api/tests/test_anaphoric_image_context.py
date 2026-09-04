"""Referencias anafóricas («ese ejemplo», «esa idea») deben resolver contexto visual del hilo."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.chat_image_generation import effective_user_prompt, run_chat_image_generation
from app.services.chat_intents import (
    is_vague_image_subject,
    resolve_anaphoric_image_prompt,
)

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
            "Listo, vamos con eso. Un espejo largo con luz LED cambiaría bastante "
            "la percepción del espacio. Dependiendo de dónde lo coloques:\n"
            "- Vertical en toda la pared: multiplica altura y profundidad.\n"
            "- Luz fría vs cálida cambia el ambiente del baño.\n"
            "- Refleja luz hacia zonas oscuras del vanity."
        ),
    },
]


def test_vague_image_subject_detects_ese_ejemplo():
    assert is_vague_image_subject("ese ejemplo para ver cómo se vería")
    assert is_vague_image_subject("esa idea")
    assert not is_vague_image_subject(
        "un baño moderno con espejo largo LED y encimera de granito"
    )


def test_resolve_anaphoric_from_bathroom_thread():
    msg = "Genera una imagen de ese ejemplo para ver cómo se vería"
    resolved = resolve_anaphoric_image_prompt(msg, BATHROOM_HISTORY)
    assert resolved
    low = resolved.lower()
    assert "espejo" in low
    assert "led" in low or "luz" in low


def test_effective_user_prompt_bathroom_example():
    msg = "Genera una imagen de ese ejemplo para ver cómo se vería"
    resolved = effective_user_prompt(msg, BATHROOM_HISTORY)
    low = resolved.lower()
    assert "espejo" in low
    assert "ese ejemplo" not in low


@patch("app.services.gemini_images.generate_image")
def test_run_generation_uses_bathroom_context_not_random_scene(mock_gen: MagicMock):
    mock_gen.return_value = {
        "ok": True,
        "url": "https://example.com/bathroom.jpg",
        "caption": "Baño",
        "quality": "standard",
    }
    msg = "Genera una imagen de ese ejemplo para ver cómo se vería"
    result = run_chat_image_generation(
        "user-1",
        "conv-1",
        msg,
        BATHROOM_HISTORY,
        plan_id="elite",
    )
    assert result["ok"] is True
    mock_gen.assert_called_once()
    prompt = mock_gen.call_args.kwargs.get("prompt") or mock_gen.call_args[0][0]
    low = prompt.lower()
    assert "espejo" in low
    assert "ese ejemplo" not in low
    assert "atardecer" not in low
    assert "cliff" not in low


CED_CAROUSEL_HISTORY = [
    {
        "role": "user",
        "content": (
            "Idea de carrusel — 3 imágenes:\n"
            "Imagen 1 — Hook visual. Texto overlay: "
            '"Tu asistente de IA no es un chatbot genérico". '
            "Visual: silueta elegante de una interfaz futurista tipo Jarvis, "
            "líneas limpias, azul/plata, minimalista. "
            'Subtexto: "Conoce CED — Castillo de la Evolución Digital".'
        ),
    },
    {
        "role": "user",
        "content": (
            "Ok has esa primera imagen pero que ced con los tonos de ced "
            "y el rostro holografico de ced"
        ),
    },
    {
        "role": "assistant",
        "content": (
            "**Concepto — Imagen 1 del Carrusel**\n"
            "- Fondo: Negro profundo con destellos azul eléctrico\n"
            "- Centro: Rostro holográfico de CED, líneas de luz azul/plata, "
            "estilo Jarvis, semi-transparente\n"
            "- Paleta CED: Azul eléctrico #00BFFF + Plata + Negro + toques dorados\n"
            '- Texto overlay: "Tu asistente de IA no es un chatbot genérico"\n'
            "¿Le damos con este concepto o quieres ajustar algo?"
        ),
    },
]


def test_esa_imagen_is_vague_and_points_at_prior():
    from app.services.chat_intents import (
        is_anaphoric_image_subject,
        is_generate_image_intent,
        is_image_meta_talk,
        points_at_prior_visual,
    )

    assert is_vague_image_subject("esa imagen")
    assert is_anaphoric_image_subject("esa imagen")
    assert points_at_prior_visual("Ok genera esa imagen")
    assert points_at_prior_visual("genera esa primera imagen pero que ced")
    assert is_image_meta_talk("Ok genera esa imagen") is False
    assert is_generate_image_intent("Ok genera esa imagen") is True


def test_carousel_generate_esa_imagen_keeps_concept_and_overlay():
    msg = "Ok genera esa imagen"
    resolved = effective_user_prompt(msg, CED_CAROUSEL_HISTORY)
    low = resolved.lower()
    assert "hologr" in low
    assert "00bfff" in low or "azul eléctrico" in low or "azul electrico" in low
    assert "chatbot genérico" in low or "chatbot generico" in low
    assert "jarvis" in low
    assert "escena pedida por el usuario" not in low
    assert "instrucciones actuales" not in low


def test_carousel_first_generate_merges_original_brief():
    history = CED_CAROUSEL_HISTORY[:1]
    msg = (
        "Ok genera esa primera imagen pero que ced con los tonos de ced "
        "y el rostro holografico de ced"
    )
    resolved = effective_user_prompt(msg, history)
    low = resolved.lower()
    assert "chatbot genérico" in low or "chatbot generico" in low
    assert "hologr" in low
    assert "castillo" in low or "ced" in low


def test_standalone_scene_does_not_merge_unrelated_history():
    history = [
        {"role": "user", "content": "Okay genera un robot corriendo a toda velocidad"},
        {"role": "assistant", "content": "Listo. Aquí está tu imagen del robot."},
    ]
    msg = "generame una imagen de un águila volando sobre un cielo lluvioso"
    resolved = effective_user_prompt(msg, history)
    low = resolved.lower()
    assert "águila" in low or "aguila" in low
    assert "robot" not in low


@patch("app.services.gemini_images.generate_image")
def test_run_generation_uses_carousel_concept_not_thin_command(mock_gen: MagicMock):
    mock_gen.return_value = {
        "ok": True,
        "url": "https://example.com/ced.jpg",
        "caption": "CED",
        "quality": "standard",
    }
    msg = "Ok genera esa imagen"
    result = run_chat_image_generation(
        "user-1",
        "conv-ced",
        msg,
        CED_CAROUSEL_HISTORY,
        plan_id="elite",
    )
    assert result["ok"] is True
    prompt = mock_gen.call_args.kwargs.get("prompt") or ""
    low = prompt.lower()
    assert "hologr" in low
    assert "chatbot genérico" in low or "chatbot generico" in low
    assert "esa imagen" not in low or "hologr" in low
