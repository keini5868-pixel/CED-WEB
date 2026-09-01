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
