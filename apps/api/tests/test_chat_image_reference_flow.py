"""Tests — generación de imágenes con referencia de sesión (chat normal y avanzado)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.chat_image_generation import (
    build_enriched_generation_context,
    extract_vision_context_from_history,
    run_chat_image_generation,
    should_take_direct_image_path,
    should_use_reference_generation,
)
from app.services.chat_intents import (
    parse_followup_image_prompt,
    user_requests_prior_reference,
)
from app.services.marketing_creative import resolve_image_creation_from_text
from app.services.publish_image_context import (
    clear_session_image,
    get_session_vision_analysis,
    register_text_chat_image,
    resolve_reference_image_bytes,
    set_session_vision_analysis,
)

USER = "user-img-test"
CONV = "conv-img-test"
PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xdb\x00\x00\x00\x00IEND\xaeB`\x82"
)

VISION_REPLY = (
    "**Qué es** — Flyer promocional DUGLE STUDIO.\n"
    "**Detalle visible** — Nombre «DUGLE STUDIO», precios $49 / $79 / $99, fondo oscuro.\n"
    "**Contexto** — Estilo flyer vertical.\n"
    "**Observaciones** — Tipografía sans-serif blanca."
)

HISTORY_AFTER_ANALYSIS = [
    {"role": "user", "content": "analiza esta imagen"},
    {"role": "model", "content": VISION_REPLY},
]


@pytest.fixture(autouse=True)
def _clean_image_session():
    clear_session_image(USER, CONV)
    yield
    clear_session_image(USER, CONV)


def test_register_text_chat_image_stores_bytes_for_followup():
    register_text_chat_image(USER, CONV, PNG, "image/png", filename="ref.png")
    resolved = resolve_reference_image_bytes(USER, CONV)
    assert resolved is not None
    data, mime = resolved
    assert data == PNG
    assert mime == "image/png"


def test_vision_analysis_cached_and_injected_in_context():
    set_session_vision_analysis(USER, CONV, VISION_REPLY)
    cached = get_session_vision_analysis(USER, CONV)
    assert "DUGLE STUDIO" in cached
    ctx = build_enriched_generation_context(
        "genera flyer igual con mismos precios",
        HISTORY_AFTER_ANALYSIS,
        user_id=USER,
        conversation_id=CONV,
    )
    assert "DUGLE STUDIO" in ctx
    assert "Instrucciones actuales del usuario" in ctx


def test_extract_vision_context_from_history():
    text = extract_vision_context_from_history(HISTORY_AFTER_ANALYSIS)
    assert "Qué es" in text
    assert "$49" in text


def test_user_requests_prior_reference_detects_phrases():
    assert user_requests_prior_reference("créame una imagen igual a la que te pasé")
    assert user_requests_prior_reference("mismos precios y mismo diseño")
    assert not user_requests_prior_reference("hola, cómo estás")


def test_resolve_image_creation_uses_reference_flag():
    register_text_chat_image(USER, CONV, PNG, "image/png")
    msg = (
        "genera una imagen igual a la que te pasé con el nombre DUGLE STUDIO, "
        "los mismos precios y diseño estilo flyer"
    )
    resolved = resolve_image_creation_from_text(
        msg,
        HISTORY_AFTER_ANALYSIS,
        has_reference_image=True,
    )
    assert resolved is not None
    assert "Usa la foto adjunta" in resolved["internal_prompt"]
    assert "DUGLE STUDIO" in resolved["internal_prompt"] or "STUDIO" in resolved["internal_prompt"]


@patch("app.services.image_reference_generator.generate_image_with_reference")
def test_run_generation_uses_reference_bytes(mock_ref: MagicMock):
    register_text_chat_image(USER, CONV, PNG, "image/png")
    set_session_vision_analysis(USER, CONV, VISION_REPLY)
    mock_ref.return_value = {
        "ok": True,
        "url": "https://example.com/gen.jpg",
        "quality": "standard",
    }

    msg = "genera creativo igual a la referencia con nombre DUGLE STUDIO y precios $49 $79 $99"
    result = run_chat_image_generation(USER, CONV, msg, HISTORY_AFTER_ANALYSIS, plan_id="elite")

    assert result["ok"] is True
    assert result["url"]
    assert result["used_reference"] is True
    mock_ref.assert_called_once()
    call_kw = mock_ref.call_args.kwargs
    assert call_kw["reference_image"] == PNG
    prompt = call_kw["prompt"]
    assert "DUGLE STUDIO" in prompt or "STUDIO" in prompt or "49" in prompt


@patch("app.services.gemini_images.generate_image")
def test_run_generation_plain_without_reference(mock_gen: MagicMock):
    mock_gen.return_value = {
        "ok": True,
        "url": "https://example.com/plain.jpg",
        "caption": "Atardecer",
        "quality": "standard",
    }
    msg = "genera una imagen de un atardecer en la playa estilo fotorrealista"
    result = run_chat_image_generation(USER, CONV, msg, [], plan_id="elite")

    assert result["ok"] is True
    assert result["url"]
    assert result["used_reference"] is False
    mock_gen.assert_called_once()


@patch("app.services.image_reference_generator.generate_image_with_reference")
def test_run_generation_failure_never_returns_false_success(mock_ref: MagicMock):
    register_text_chat_image(USER, CONV, PNG, "image/png")
    mock_ref.return_value = {"ok": False, "error": "Límite diario alcanzado", "code": "quota_exhausted"}

    msg = "genera otra imagen igual a la referencia con DUGLE STUDIO"
    result = run_chat_image_generation(USER, CONV, msg, HISTORY_AFTER_ANALYSIS, plan_id="elite")

    assert result["ok"] is False
    assert not result.get("url")
    assert "Límite" in result["reply"] or "No pude generar" in result["reply"]
    assert "Listo, señor" not in result["reply"]


@patch("app.services.image_reference_generator.generate_image_with_reference")
def test_repeat_generations_stay_on_direct_path(mock_ref: MagicMock):
    register_text_chat_image(USER, CONV, PNG, "image/png")
    set_session_vision_analysis(USER, CONV, VISION_REPLY)
    mock_ref.return_value = {
        "ok": True,
        "url": "https://example.com/repeat.jpg",
        "quality": "standard",
    }

    history = list(HISTORY_AFTER_ANALYSIS)
    prompts = [
        "genera flyer DUGLE STUDIO con precios $49 $79 $99",
        "otra vez igual con los mismos precios",
        "hazlo de nuevo mismo diseño",
        "genera otra imagen creativo referencia",
    ]
    for prompt in prompts:
        assert should_take_direct_image_path(prompt, history)
        result = run_chat_image_generation(USER, CONV, prompt, history, plan_id="elite")
        assert result["ok"] is True, result
        assert result["url"]
        history.append({"role": "user", "content": prompt})
        history.append(
            {
                "role": "model",
                "content": "Listo, señor. Aquí está su creativo — imagen generada.",
            }
        )

    assert mock_ref.call_count == len(prompts)


def test_followup_prompt_after_vision_analysis():
    followup = parse_followup_image_prompt(
        "otra vez con los mismos precios",
        HISTORY_AFTER_ANALYSIS,
    )
    assert followup == "otra vez con los mismos precios"


def test_should_use_reference_when_session_has_upload():
    register_text_chat_image(USER, CONV, PNG, "image/png")
    assert should_use_reference_generation(
        "genera creativo estilo flyer con DUGLE STUDIO",
        HISTORY_AFTER_ANALYSIS,
        user_id=USER,
        conversation_id=CONV,
    )


@patch("app.services.chat_image_generation.run_chat_image_generation")
@patch("app.services.text_chat.supabase_db")
def test_text_chat_direct_path_returns_image_not_template(mock_db: MagicMock, mock_run: MagicMock):
    from app.services.text_chat import send_message

    mock_db.get_subscription.return_value = {"plan_id": "elite"}
    mock_db.get_profile.return_value = {"email": "u@test.com", "role": "user"}
    mock_db.get_conversation.return_value = {"id": CONV, "channel": "text"}
    mock_db.get_conversation_messages.return_value = HISTORY_AFTER_ANALYSIS
    mock_db.append_message.return_value = None
    mock_db.create_conversation.return_value = {"id": CONV}

    register_text_chat_image(USER, CONV, PNG, "image/png")
    mock_run.return_value = {
        "ok": True,
        "url": "https://example.com/out.jpg",
        "reply": "Listo, señor. Aquí está su creativo.",
        "caption": "Flyer — DUGLE STUDIO",
        "quality": "standard",
        "used_reference": True,
    }

    with patch("app.services.chat_rate_limit.check_chat_rate_limit", return_value=(True, 0)):
        with patch("app.deps.plan_access.chat_message_limit", return_value=-1):
            with patch("app.services.text_chat._cached_messages_today", return_value=0):
                out = send_message(
                    USER,
                    content="genera imagen igual a la referencia DUGLE STUDIO precios $49",
                    conversation_id=CONV,
                )

    assert out.get("image", {}).get("url")
    mock_run.assert_called_once()


@patch("app.services.chat_image_generation.run_chat_image_generation")
def test_advanced_direct_image_followup(mock_run: MagicMock):
    from app.services.advanced_mode.service import _try_direct_image

    register_text_chat_image(USER, CONV, PNG, "image/png")
    mock_run.return_value = {
        "ok": True,
        "url": "https://example.com/adv.jpg",
        "reply": "Listo, señor. Aquí está su creativo.",
        "caption": "Creativo",
        "quality": "standard",
        "used_reference": True,
    }

    result = _try_direct_image(
        USER,
        "otra vez igual con mismos precios DUGLE STUDIO",
        HISTORY_AFTER_ANALYSIS,
        CONV,
    )
    assert result is not None
    assert result.get("image", {}).get("url")
    mock_run.assert_called_once()
