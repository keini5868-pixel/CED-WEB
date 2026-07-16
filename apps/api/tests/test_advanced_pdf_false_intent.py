"""Tests — modo avanzado no debe generar PDF por mencionar la palabra en una lista."""

from __future__ import annotations

from unittest.mock import patch

from app.services.advanced_mode.intents import needs_advanced_full_pipeline
from app.services.advanced_mode.service import send_advanced_message
from app.services.chat_intents import (
    is_generate_image_intent,
    is_pdf_intent,
    resolve_pdf_request,
)

CAPABILITY_LIST_MSG = (
    "Dame una lista donde especifique así por número, por ejemplo número uno "
    "publicación en redes, número dos sistema avanzado de análisis profundo, "
    "número tres generación de imágenes y PDF, y así sucesivamente todas las "
    "habilidades y las herramientas que tiene el sistema CED."
)


def test_capability_list_not_pdf_or_image_intent():
    assert not is_pdf_intent(CAPABILITY_LIST_MSG)
    assert resolve_pdf_request(CAPABILITY_LIST_MSG, []) is None
    assert not is_generate_image_intent(CAPABILITY_LIST_MSG)
    assert not needs_advanced_full_pipeline(CAPABILITY_LIST_MSG, [])


def test_send_advanced_message_capability_list_does_not_create_pdf():
    """Prueba real del path de modo avanzado con el mensaje exacto del bug."""
    with (
        patch(
            "app.services.advanced_mode.service.require_anthropic_api_key",
            return_value="sk-test",
        ),
        patch(
            "app.services.advanced_mode.service._complete_chat_with_tools",
            return_value=("should-not-run", None, None),
        ) as mock_claude,
        patch("app.services.text_chat._execute_direct_pdf") as mock_pdf,
        patch("app.services.text_chat.store_pdf_with_timeout") as mock_store,
        patch(
            "app.services.chat_image_generation.run_chat_image_generation"
        ) as mock_img,
    ):
        out = send_advanced_message(
            "user-adv-pdf-bug",
            message=CAPABILITY_LIST_MSG,
            history=[],
            conversation_id="conv-adv-pdf-bug",
        )

    assert out.get("pdf") in (None, {})
    assert "Listo. PDF" not in (out.get("response") or "")
    assert "WhatsApp" not in (out.get("response") or "")
    assert "Gmail" in out["response"] or "1." in out["response"]
    mock_claude.assert_not_called()
    mock_pdf.assert_not_called()
    mock_store.assert_not_called()
    mock_img.assert_not_called()
