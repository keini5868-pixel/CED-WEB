"""Regresión — imagen/PDF ganan sobre módulos con palabras trampa (tiempo, cita, correo).

Bug: «Genera una imagen con la frase 'inevitablemente el tiempo va a pasar'»
activaba clima porque ``is_environment_intent`` matcheaba ``\\btiempo\\b`` ANTES
de la ruta de imagen en ``send_message`` (el stream fuerza blocking para imagen).
Misma categoría: PDF con «cita»/«correo» vs calendario/Gmail.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.modules.calendar_module import is_calendar_intent
from app.modules.environment_module import is_environment_action_request, is_environment_intent
from app.modules.finance_module import is_finance_intent
from app.modules.gmail_module import is_gmail_intent
from app.services.ced_orchestrator import detect_module, detect_voice_module_intent
from app.services.chat_image_generation import should_take_direct_image_path
from app.services.chat_intents import (
    is_creative_artifact_intent,
    is_generate_image_intent,
    is_pdf_intent,
)
from app.services.cognitive_intents import is_weather_intent
from app.services.module_detector import detect_intent

# Pedidos creativos con palabras trampa en el texto citado / cuerpo.
IMAGE_TRAP_CASES = [
    "Genera una imagen con la frase 'inevitablemente el tiempo va a pasar'",
    'Hazme un banner que diga "el tiempo es oro"',
    'genera una imagen que diga "la hora y la fecha de hoy"',
    'crea una imagen con el texto "revisa tu correo y confirma la cita"',
]

PDF_TRAP_CASES = [
    "Genera un PDF con la frase: el tiempo va a pasar",
    "Hazme un PDF que diga que tengo una cita el lunes y un correo pendiente",
    'crea un PDF que diga "la hora de la fecha de hoy"',
]

# Consultas REALES a módulos — no deben romper.
REAL_MODULE_CASES = [
    ("como esta el tiempo hoy", "environment"),
    ("que clima hace", "environment"),
    ("informacion del tiempo", "environment"),
    ("lee mis correos", "gmail"),
    ("que tengo hoy en el calendario", "calendar"),
]


@pytest.mark.parametrize("text", IMAGE_TRAP_CASES)
def test_image_trap_phrases_are_creative_not_modules(text: str) -> None:
    assert is_generate_image_intent(text) is True
    assert is_creative_artifact_intent(text) is True
    assert is_environment_intent(text) is False
    assert is_environment_action_request(text) is False
    assert is_weather_intent(text) is False
    assert is_calendar_intent(text) is False
    assert is_gmail_intent(text) is False
    assert is_finance_intent(text) is False
    assert should_take_direct_image_path(text, []) is True


@pytest.mark.parametrize("text", PDF_TRAP_CASES)
def test_pdf_trap_phrases_are_creative_not_modules(text: str) -> None:
    assert is_pdf_intent(text) is True
    assert is_creative_artifact_intent(text) is True
    assert is_environment_intent(text) is False
    assert is_weather_intent(text) is False
    assert is_calendar_intent(text) is False
    assert is_gmail_intent(text) is False
    assert is_finance_intent(text) is False


@pytest.mark.parametrize("text", IMAGE_TRAP_CASES)
def test_voice_routes_image_trap_to_image_gen(text: str) -> None:
    assert detect_voice_module_intent(text, []) == "image_gen"
    assert detect_module(text, []) == "image_gen"
    det = detect_intent(text, run_stage2=False)
    assert det.module == "image_gen"
    assert det.activate is True


@pytest.mark.parametrize("text", PDF_TRAP_CASES)
def test_voice_routes_pdf_trap_to_pdf(text: str) -> None:
    assert detect_voice_module_intent(text, []) == "pdf"
    assert detect_module(text, []) == "pdf"
    det = detect_intent(text, run_stage2=False)
    assert det.module == "pdf"
    assert det.activate is True


@pytest.mark.parametrize(("text", "module"), REAL_MODULE_CASES)
def test_real_module_queries_still_work(text: str, module: str) -> None:
    assert is_creative_artifact_intent(text) is False
    if module == "environment":
        assert is_environment_intent(text) is True
        assert detect_voice_module_intent(text, []) == "environment"
    elif module == "gmail":
        assert is_gmail_intent(text) is True
        assert detect_voice_module_intent(text, []) == "gmail"
    elif module == "calendar":
        assert is_calendar_intent(text) is True
        assert detect_voice_module_intent(text, []) == "calendar"


def test_send_message_image_with_tiempo_does_not_call_environment() -> None:
    """Chat (blocking path): imagen con «tiempo» no debe invocar clima."""
    from app.services.text_chat import send_message

    text = "Genera una imagen con la frase 'inevitablemente el tiempo va a pasar'"
    env_calls: list[str] = []

    with (
        patch("app.services.text_chat.supabase_db") as mock_db,
        patch("app.services.chat_rate_limit.check_chat_rate_limit", return_value=(True, 0)),
        patch("app.deps.plan_access.chat_message_limit", return_value=-1),
        patch("app.services.text_chat.chat_status", return_value={"blocked": False, "used": 0, "limit": -1}),
        patch("app.services.text_chat._cached_messages_today", return_value=0),
        patch(
            "app.modules.environment_module.handle_environment_query_sync",
            side_effect=lambda *a, **k: env_calls.append("env") or {"spoken": "clima"},
        ),
        patch(
            "app.services.chat_image_generation.run_chat_image_generation",
            return_value={
                "ok": True,
                "url": "https://example.com/img.png",
                "reply": "Listo. Aquí está tu imagen generada.",
                "caption": "Imagen",
                "quality": "text",
                "provider": "ideogram",
                "ideogram_used": True,
            },
        ) as mock_img,
    ):
        mock_db.get_profile.return_value = {"email": "u@test.com", "role": "user"}
        mock_db.get_subscription.return_value = {"plan_id": "elite"}
        mock_db.get_conversation.return_value = {"id": "c1", "channel": "text"}
        mock_db.get_conversation_messages.return_value = []
        mock_db.create_conversation.return_value = {"id": "c1"}
        mock_db.append_message.return_value = None

        out = send_message("user-trap", content=text, conversation_id="c1")

    assert not env_calls, "clima no debió ejecutarse"
    mock_img.assert_called_once()
    assert out.get("image", {}).get("url")
    assert "clima" not in (out.get("reply") or "").lower()


def test_send_message_pdf_with_cita_correo_does_not_call_calendar_or_gmail() -> None:
    from app.services.text_chat import send_message

    text = "Hazme un PDF que diga que tengo una cita el lunes y un correo pendiente"
    cal_calls: list[str] = []
    gmail_calls: list[str] = []

    with (
        patch("app.services.text_chat.supabase_db") as mock_db,
        patch("app.services.chat_rate_limit.check_chat_rate_limit", return_value=(True, 0)),
        patch("app.deps.plan_access.chat_message_limit", return_value=-1),
        patch("app.services.text_chat.chat_status", return_value={"blocked": False, "used": 0, "limit": -1}),
        patch("app.services.text_chat._cached_messages_today", return_value=0),
        patch(
            "app.modules.calendar_module.handle_calendar_query_sync",
            side_effect=lambda *a, **k: cal_calls.append("cal") or {"spoken": "cita"},
        ),
        patch(
            "app.modules.gmail_module.handle_gmail_query_sync",
            side_effect=lambda *a, **k: gmail_calls.append("gmail") or {"spoken": "correo"},
        ),
        patch(
            "app.services.text_chat._try_direct_pdf_from_context",
            return_value=(
                "PDF listo.",
                {"file_id": "pdf-1", "title": "Doc", "download_path": "/v1/pdf/download/pdf-1"},
            ),
        ) as mock_pdf,
        patch("app.services.text_chat.resolve_pdf_detail_for_turn", return_value="brief"),
        patch("app.services.text_chat.resolve_pdf_request", return_value=("Doc", "contenido")),
        patch("app.services.text_chat.prior_pdf_user_request", return_value=None),
    ):
        mock_db.get_profile.return_value = {"email": "u@test.com", "role": "user"}
        mock_db.get_subscription.return_value = {"plan_id": "elite"}
        mock_db.get_conversation.return_value = {"id": "c1", "channel": "text"}
        mock_db.get_conversation_messages.return_value = []
        mock_db.create_conversation.return_value = {"id": "c1"}
        mock_db.append_message.return_value = None

        out = send_message("user-trap-pdf", content=text, conversation_id="c1")

    assert not cal_calls
    assert not gmail_calls
    mock_pdf.assert_called_once()
    assert out.get("pdf", {}).get("file_id") == "pdf-1"


def test_advanced_direct_image_with_tiempo_trap() -> None:
    from app.services.advanced_mode.service import _try_direct_image

    text = "Genera una imagen con la frase 'inevitablemente el tiempo va a pasar'"
    with patch(
        "app.services.chat_image_generation.run_chat_image_generation",
        return_value={
            "ok": True,
            "url": "https://example.com/adv.png",
            "reply": "Listo.",
            "caption": "Img",
            "quality": "text",
        },
    ) as mock_gen:
        result = _try_direct_image("user-adv", text, [], "conv-adv")

    assert result is not None
    assert result.get("image", {}).get("url")
    mock_gen.assert_called_once()


def test_can_stream_forces_blocking_for_image_but_weather_no_longer_wins() -> None:
    """Stream sigue yendo a blocking para imagen; weather intent ya no es True."""
    from app.services.text_chat import _can_stream_chat_text

    text = "Genera una imagen con la frase 'inevitablemente el tiempo va a pasar'"
    assert is_weather_intent(text) is False
    assert _can_stream_chat_text(text) is False  # blocking → send_message (ya prioriza imagen)
