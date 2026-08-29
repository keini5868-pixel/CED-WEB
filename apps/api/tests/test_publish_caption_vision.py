"""Caption de publicación debe basarse en la imagen, no en historial FitLine."""

from __future__ import annotations

from unittest.mock import patch

from app.services.publish_image_context import (
    begin_publish_flow,
    register_text_chat_image_url,
    set_session_vision_analysis,
)
from app.services.text_chat import _suggest_social_caption
from app.services.text_publish_flow import handle_publish_flow_turn


UID = "caption-vision-user"
CONV = "caption-vision-conv"


def test_suggest_caption_uses_vision_not_fitline_history():
    register_text_chat_image_url(UID, CONV, "https://example.com/sci-fi-ced.jpg")
    set_session_vision_analysis(
        UID,
        CONV,
        'Centro de comando futurista con holograma azul. Texto legible: '
        '"de nuevo comienza" "el sistema C" "ha llegado".',
    )
    history = [
        {
            "role": "user",
            "content": "Háblame de Activize y FitLine",
        },
        {
            "role": "model",
            "content": "Activize potencia la microcirculación...",
        },
        {"role": "user", "content": "publica esta imagen en instagram"},
    ]

    with patch(
        "app.services.text_chat._gemini_simple_reply",
        return_value=(
            "El sistema C ha llegado\n\n"
            "Un centro de comando holográfico marca el reinicio. "
            "#CED #SistemaC #EvoluciónDigital"
        ),
    ) as mock_gemini:
        draft = _suggest_social_caption(
            "instagram",
            "si ayudame con la descripcion",
            history,
            user_id=UID,
            conversation_id=CONV,
        )

    assert "Activize" not in draft
    assert "microcirculación" not in draft.lower()
    assert "sistema" in draft.lower() or "CED" in draft
    # Vision must be in the prompt sent to Gemini
    user_msg = mock_gemini.call_args.kwargs.get("messages")[-1]["content"]
    assert "ANÁLISIS VISUAL" in user_msg
    assert "el sistema C" in user_msg
    system = mock_gemini.call_args.kwargs.get("system") or ""
    assert "PROHIBIDO inventar FitLine" in system


def test_publish_help_with_vision_does_not_leak_fitline_copy():
    register_text_chat_image_url(UID, CONV, "https://example.com/sci-fi-ced.jpg")
    set_session_vision_analysis(
        UID,
        CONV,
        'Holograma azul. Texto: "el sistema C ha llegado".',
    )
    begin_publish_flow(
        UID,
        CONV,
        platform="instagram",
        caption_draft="",
        stage="awaiting_caption_choice",
    )
    history = [
        {"role": "user", "content": "publica en instagram"},
        {
            "role": "model",
            "content": "Imagen recibida. ¿Ayuda con título y descripción?",
        },
    ]

    with patch(
        "app.services.text_chat._suggest_social_caption",
        return_value=(
            "El sistema C ha llegado\n\nNueva era digital. #CED #SistemaC"
        ),
    ):
        # Use real suggest through wrapper that calls vision-aware function
        def suggest(platform, user_text, hist):
            return _suggest_social_caption(
                platform,
                user_text,
                hist,
                user_id=UID,
                conversation_id=CONV,
            )

        with patch(
            "app.services.text_chat._gemini_simple_reply",
            return_value=(
                "El sistema C ha llegado\n\nNueva era digital. #CED #SistemaC"
            ),
        ):
            reply = handle_publish_flow_turn(
                UID,
                CONV,
                "si ayudame con la descripcion",
                history=history,
                run_tool=lambda *a, **k: "{}",
                suggest_caption=suggest,
            )

    assert reply
    assert "Activize" not in reply
    assert "sistema C" in reply.lower() or "CED" in reply
