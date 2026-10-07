"""Bugs de voz/chat: prompt partido, referencia de un turno, copy literal."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.chat_image_generation import (
    heard_is_prompt_fragment,
    image_prompt_covers_request,
    join_same_image_request_utterances,
    pick_voice_image_source_prompt,
    run_chat_image_generation,
    should_use_reference_generation,
    utterance_too_thin_for_prompt,
)
from app.services.chat_intents import (
    user_requests_image_edit,
    user_requests_new_image_piece,
    wants_image_reference_edit,
)
from app.services.publish_image_context import (
    clear_session_image,
    register_text_chat_image,
    register_text_chat_image_url,
)

USER = "user-img-prompt-src"
CONV = "conv-img-prompt-src"
PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xdb\x00\x00\x00\x00IEND\xaeB`\x82"
)

NEW_FLYER = (
    "genera un flyer con fondo oscuro y el texto "
    "'Inevitablemente el tiempo va a pasar, no te dediques a perderlo' "
    "en azul cian con sombra blanca opaca"
)
EDIT_BIGGER = "ahora hazlo más grande"
OTHER_FLYER = 'genera otro flyer con fondo azul y la frase "La disciplina vence al reloj"'


@pytest.fixture(autouse=True)
def _clean_session():
    clear_session_image(USER, CONV)
    yield
    clear_session_image(USER, CONV)


def test_new_flyer_with_que_diga_is_not_a_reference_edit():
    msg = (
        "genera un flyer con un fondo oscuro que tenga un texto que diga "
        "inevitablemente el tiempo va a pasar no te dediques a perderlo"
    )
    assert user_requests_new_image_piece(msg) is True
    assert wants_image_reference_edit(msg) is False
    assert user_requests_image_edit(msg) is False
    assert user_requests_image_edit("ahora hazlo más grande") is True
    assert wants_image_reference_edit("ahora hazlo más grande") is True


def test_pick_voice_prompt_uses_args_not_blanco_fragment():
    full = (
        'Flyer de fondo oscuro con el texto "Inevitablemente el tiempo va a pasar, '
        'no te dediques a perderlo" en relieve blanco.'
    )
    history = [
        {
            "role": "user",
            "content": (
                "Flyer de fondo oscuro con el texto Inevitablemente el tiempo "
                "va a pasar, no te dediques a perderlo en relieve"
            ),
        },
        {"role": "user", "content": "blanco."},
    ]
    joined = join_same_image_request_utterances(history)
    assert "Inevitablemente" in joined
    assert utterance_too_thin_for_prompt("blanco.", full) is True
    assert heard_is_prompt_fragment("blanco.", full) is True
    chosen = pick_voice_image_source_prompt(
        args_prompt=full,
        heard="blanco.",
        history=history,
    )
    assert chosen == full
    assert image_prompt_covers_request(chosen, full) is True


@patch("app.services.gemini_images.generate_image")
@patch("app.services.image_reference_generator.generate_image_with_reference")
def test_new_then_edit_then_new_piece_does_not_inherit(
    mock_ref: MagicMock, mock_gen: MagicMock
):
    mock_gen.return_value = {
        "ok": True,
        "url": "https://example.com/flyer-1.png",
        "quality": "text",
        "provider": "gpt_image",
        "ideogram_used": True,
    }
    mock_ref.return_value = {
        "ok": True,
        "url": "https://example.com/flyer-edit.png",
        "quality": "standard",
    }

    first = run_chat_image_generation(USER, CONV, NEW_FLYER, [], plan_id="elite")
    assert first["ok"] is True
    assert first["used_reference"] is False
    mock_ref.assert_not_called()
    register_text_chat_image(USER, CONV, PNG, "image/png")
    register_text_chat_image_url(USER, CONV, str(first["url"]), prompt=NEW_FLYER)
    gen_kw = mock_gen.call_args.kwargs
    assert gen_kw.get("reference_image") in (None, "")
    assert gen_kw.get("prefer_ideogram") is True
    prompt = str(gen_kw.get("prompt") or "")
    assert "Inevitablemente el tiempo va a pasar, no te dediques a perderlo" in prompt
    assert "no people" in prompt.lower() or "sin personas" in prompt.lower()
    assert "sombra blanca" in prompt.lower() or "shadow must be white" in prompt.lower()

    history = [
        {"role": "user", "content": NEW_FLYER},
        {"role": "assistant", "content": "Listo. Aquí está tu imagen generada."},
    ]
    mock_gen.reset_mock()
    edit = run_chat_image_generation(USER, CONV, EDIT_BIGGER, history, plan_id="elite")
    assert edit["ok"] is True
    assert edit["used_reference"] is True
    assert mock_ref.called or (
        mock_gen.called and mock_gen.call_args.kwargs.get("reference_image")
    )

    mock_ref.reset_mock()
    mock_gen.reset_mock()
    mock_gen.return_value = {
        "ok": True,
        "url": "https://example.com/flyer-2.png",
        "quality": "text",
        "provider": "gpt_image",
        "ideogram_used": True,
    }
    history2 = history + [
        {"role": "user", "content": EDIT_BIGGER},
        {"role": "assistant", "content": "Listo. Aquí está tu imagen con los cambios pedidos."},
    ]
    assert should_use_reference_generation(
        OTHER_FLYER, history2, user_id=USER, conversation_id=CONV
    ) is False
    third = run_chat_image_generation(USER, CONV, OTHER_FLYER, history2, plan_id="elite")
    assert third["ok"] is True
    assert third["used_reference"] is False
    mock_ref.assert_not_called()
    third_kw = mock_gen.call_args.kwargs
    assert third_kw.get("reference_image") in (None, "")
    assert "La disciplina vence al reloj" in str(third_kw.get("prompt") or "")


def test_failed_or_mismatched_image_is_not_edit_reference():
    register_text_chat_image(USER, CONV, PNG, "image/png")
    register_text_chat_image_url(
        USER, CONV, "https://example.com/bad.png", prompt="blanco."
    )
    from app.services.publish_image_context import mark_session_image_unusable_for_edit

    mark_session_image_unusable_for_edit(USER, CONV, reason="mismatch")
    assert should_use_reference_generation(
        "ahora hazlo más grande",
        [{"role": "user", "content": "genera un flyer"}, {"role": "assistant", "content": "Listo."}],
        user_id=USER,
        conversation_id=CONV,
    ) is False


def test_execute_generate_image_split_turn_keeps_full_args_prompt():
    import asyncio

    from app.services.retell_native_pilot import execute_generate_image_tool

    full = (
        'Flyer de fondo oscuro con el texto "Inevitablemente el tiempo va a pasar, '
        'no te dediques a perderlo" en relieve blanco.'
    )

    async def run():
        with patch(
            "app.services.voice_tool_executor.execute_voice_tool",
            new_callable=AsyncMock,
            return_value={
                "ok": True,
                "url": "https://cdn.example.com/ok.png",
                "prompt_used": full,
                "published": True,
            },
        ) as mock_exec:
            out = await execute_generate_image_tool(
                user_id="u-split",
                payload={
                    "call": {
                        "call_id": "call_d7c714ca6440cd14b6e4404e222",
                        "transcript_object": [
                            {
                                "role": "user",
                                "content": (
                                    "Flyer de fondo oscuro con el texto Inevitablemente "
                                    "el tiempo va a pasar, no te dediques a perderlo en relieve"
                                ),
                            },
                            {"role": "agent", "content": "Perfecto, señor. Estoy creando su imagen."},
                            {"role": "user", "content": "blanco."},
                        ],
                    },
                },
                args={"prompt": full},
            )
            passed = mock_exec.await_args.args[2]
            assert passed["prompt"] == full
            assert out["ok"] is True
            assert out["published"] is True
            assert "prompt_used=" in out["result"]
            assert "Inevitablemente" in out["result"]
            assert 'prompt_used="blanco.' not in out["result"]

    asyncio.run(run())
