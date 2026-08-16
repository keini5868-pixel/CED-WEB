"""Tests — `run_chat_image_generation` pasa `prefer_ideogram` y ajusta el aviso final
según el proveedor real usado (Gemini vs Ideogram). Cubre voz + chat normal + chat
avanzado porque los tres canales llaman a esta misma función compartida."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.chat_image_generation import run_chat_image_generation
from app.services.publish_image_context import clear_session_image

USER = "user-ideogram-wiring"
CONV = "conv-ideogram-wiring"


def setup_function(_fn):
    clear_session_image(USER, CONV)


def teardown_function(_fn):
    clear_session_image(USER, CONV)


@patch("app.services.gemini_images.generate_image")
def test_explicit_quoted_text_request_sets_prefer_ideogram_true(mock_gen: MagicMock):
    mock_gen.return_value = {
        "ok": True,
        "url": "https://example.com/banner.png",
        "caption": "Banner",
        "quality": "text",
        "provider": "ideogram",
        "ideogram_used": True,
    }
    msg = 'hazme un banner que diga "Gran Apertura"'
    result = run_chat_image_generation(USER, CONV, msg, [], plan_id="pro")

    assert result["ok"] is True
    mock_gen.assert_called_once()
    assert mock_gen.call_args.kwargs["prefer_ideogram"] is True
    # Ideogram ya renderiza texto legible — no debe llevar el aviso pensado para Gemini.
    assert "legible" not in result["reply"].lower()


@patch("app.services.gemini_images.generate_image")
def test_plain_request_without_text_sets_prefer_ideogram_false(mock_gen: MagicMock):
    mock_gen.return_value = {
        "ok": True,
        "url": "https://example.com/plain.png",
        "caption": "Atardecer",
        "quality": "standard",
        "provider": "gemini",
        "ideogram_used": False,
    }
    msg = "genera una imagen de un atardecer en la playa"
    run_chat_image_generation(USER, CONV, msg, [], plan_id="pro")

    mock_gen.assert_called_once()
    assert mock_gen.call_args.kwargs["prefer_ideogram"] is False


@patch("app.services.gemini_images.generate_image")
def test_marketing_flyer_prefers_gpt_image_for_on_image_copy(mock_gen: MagicMock):
    """Flyers siempre llevan tipografía: Nano Banana 2 falla en ortografía
    (p.ej. «equipo» sin la u). Enrutar al híbrido GPT Image / Ideogram."""
    mock_gen.return_value = {
        "ok": True,
        "url": "https://example.com/flyer.png",
        "caption": "Flyer",
        "quality": "text",
        "provider": "gpt_image",
        "ideogram_used": True,
    }
    msg = "hazme un flyer de mi taller de yoga con sus beneficios y horarios"
    run_chat_image_generation(USER, CONV, msg, [], plan_id="pro")

    mock_gen.assert_called_once()
    assert mock_gen.call_args.kwargs["prefer_ideogram"] is True


@patch("app.services.gemini_images.generate_image")
def test_soft_upsell_shown_when_free_basic_excluded_from_ideogram(mock_gen: MagicMock):
    mock_gen.return_value = {
        "ok": True,
        "url": "https://example.com/plain.png",
        "caption": "Banner",
        "quality": "standard",
        "provider": "gemini",
        "ideogram_used": False,
        "ideogram_declined_reason": "basic_excluded",
    }
    msg = 'banner que diga "Feliz cumpleaños"'
    result = run_chat_image_generation(USER, CONV, msg, [], plan_id="free_basic")

    assert result["ok"] is True
    assert "plan de pago" in result["reply"].lower()
    assert "gpt image" in result["reply"].lower()


@patch("app.services.gemini_images.generate_image")
def test_generic_gemini_fallback_keeps_existing_disclaimer(mock_gen: MagicMock):
    """Cuando Ideogram no se usó por cualquier otro motivo (no basic_excluded), debe
    conservarse el aviso honesto existente sobre texto ilegible en Gemini."""
    mock_gen.return_value = {
        "ok": True,
        "url": "https://example.com/plain.png",
        "caption": "Banner",
        "quality": "standard",
        "provider": "gemini",
        "ideogram_used": False,
        "ideogram_declined_reason": "no_quota_no_balance",
    }
    msg = 'banner que diga "Hola"'
    result = run_chat_image_generation(USER, CONV, msg, [], plan_id="pro")

    assert "legible" in result["reply"].lower() or "aviso" in result["reply"].lower()
    assert "plan de pago" not in result["reply"].lower()
