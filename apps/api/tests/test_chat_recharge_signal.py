"""Tests — recarga necesitada (imágenes/PDF) por chat de texto.

Bug real corregido: `run_chat_image_generation` perdía el campo `code` en la
respuesta de fallo (`chat_image_generation.py`), y el tool `generate_image`
de `_run_chat_tool` sobrescribía cualquier código con el genérico
`generation_failed` — el código real `needs_recharge` nunca llegaba a la
capa que decide mostrar el botón de recarga en el chat. Además, PDF por chat
(tool y ruta directa) nunca consultaba el monedero: solo decía «necesitas
plan Pro», sin ofrecer recarga como sí hace el endpoint REST equivalente.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.chat_image_generation import run_chat_image_generation
from app.services.text_chat import (
    _consume_recharge_needed,
    _execute_direct_pdf,
    _mark_recharge_needed,
    _run_chat_tool,
    send_message,
)

USER = "user-recharge-chat"
CONV = "conv-recharge-chat"


def test_mark_and_consume_recharge_needed_roundtrip():
    assert _consume_recharge_needed() is None
    _mark_recharge_needed("image", "Alcanzaste el límite de imágenes.")
    signal = _consume_recharge_needed()
    assert signal == {
        "resource": "image",
        "message": "Alcanzaste el límite de imágenes.",
    }
    # Se limpia tras leerlo — no debe filtrarse al siguiente turno.
    assert _consume_recharge_needed() is None


@patch("app.services.gemini_images.generate_image")
def test_run_chat_image_generation_preserves_needs_recharge_code(mock_gen: MagicMock):
    mock_gen.return_value = {
        "ok": False,
        "error": "Alcanzaste el límite de imágenes. Recarga desde $10 para continuar.",
        "code": "needs_recharge",
    }
    result = run_chat_image_generation(
        USER, CONV, "genera una imagen de un gato astronauta", [], plan_id="free_basic"
    )
    assert result["ok"] is False
    assert result["code"] == "needs_recharge"


@patch("app.services.chat_image_generation.run_chat_image_generation")
def test_run_chat_tool_generate_image_marks_recharge_and_keeps_code(mock_run: MagicMock):
    mock_run.return_value = {
        "ok": False,
        "error": "Alcanzaste el límite de imágenes. Recarga desde $10 para continuar.",
        "code": "needs_recharge",
    }
    with patch("app.services.text_chat.supabase_db") as mock_db:
        mock_db.get_subscription.return_value = {"plan_id": "free_basic"}
        result_json = _run_chat_tool(
            USER,
            "generate_image",
            {"prompt": "un gato astronauta"},
            conversation_id=CONV,
        )
    import json

    result = json.loads(result_json)
    assert result["ok"] is False
    assert result["code"] == "needs_recharge"
    signal = _consume_recharge_needed()
    assert signal is not None
    assert signal["resource"] == "image"


def test_run_chat_tool_generar_pdf_needs_recharge_without_balance():
    with (
        patch(
            "app.deps.plan_access.effective_plan_limits",
            return_value=(MagicMock(pdf_reports=False), "ok", False),
        ),
        patch("app.services.wallet.can_afford", return_value=False),
    ):
        result_json = _run_chat_tool(
            USER,
            "generar_pdf",
            {"title": "Reporte", "content": "Contenido de prueba suficientemente largo."},
        )
    import json

    result = json.loads(result_json)
    assert result["ok"] is False
    assert result["code"] == "needs_recharge"
    signal = _consume_recharge_needed()
    assert signal is not None
    assert signal["resource"] == "pdf"


def test_run_chat_tool_generar_pdf_charges_wallet_when_no_plan_but_has_balance():
    from types import SimpleNamespace

    artifact = SimpleNamespace(
        file_id="pdf-chat-1", filename="reporte.pdf", title="Reporte pagado"
    )
    spent: list[dict] = []
    with (
        patch(
            "app.deps.plan_access.effective_plan_limits",
            return_value=(MagicMock(pdf_reports=False), "ok", False),
        ),
        patch("app.services.wallet.can_afford", return_value=True),
        patch(
            "app.services.wallet.try_spend",
            side_effect=lambda uid, resource, units=1.0: spent.append(resource)
            or {"ok": True, "balance_usd": 4.9},
        ),
        patch(
            "app.services.text_chat.store_pdf_with_timeout",
            return_value=artifact,
        ),
    ):
        result_json = _run_chat_tool(
            USER,
            "generar_pdf",
            {"title": "Reporte pagado", "content": "Contenido de prueba suficientemente largo."},
        )
    import json

    result = json.loads(result_json)
    assert result["ok"] is True
    assert result["file_id"] == "pdf-chat-1"
    assert spent == ["pdf"]
    assert _consume_recharge_needed() is None


def test_execute_direct_pdf_needs_recharge_without_balance():
    with (
        patch(
            "app.deps.plan_access.effective_plan_limits",
            return_value=(MagicMock(pdf_reports=False), "ok", False),
        ),
        patch("app.services.wallet.can_afford", return_value=False),
    ):
        message, attachment = _execute_direct_pdf(
            USER,
            title="Reporte",
            content="Contenido de prueba suficientemente largo para el PDF.",
            history=[],
            conversation_id=CONV,
            user_request="genera un pdf con el reporte",
        )
    assert "recarga" in message.lower() or "Pro" in message
    assert attachment == {}
    signal = _consume_recharge_needed()
    assert signal is not None
    assert signal["resource"] == "pdf"


@patch("app.services.chat_image_generation.run_chat_image_generation")
@patch("app.services.text_chat.supabase_db")
def test_send_message_end_to_end_surfaces_recharge_needed_for_image(
    mock_db: MagicMock, mock_run: MagicMock
):
    """Prueba real de extremo a extremo (misma función que usa el router

    /v1/chat/send): usuario free_basic sin saldo pide una imagen → la
    respuesta HTTP final debe traer `recharge_needed` para que el frontend
    muestre el botón, no solo un texto que el usuario podría ignorar.
    """
    mock_db.get_subscription.return_value = {"plan_id": "free_basic"}
    mock_db.get_profile.return_value = {"email": "free@test.com", "role": "user"}
    mock_db.get_conversation.return_value = {"id": CONV, "channel": "text"}
    mock_db.get_conversation_messages.return_value = []
    mock_db.append_message.return_value = None
    mock_db.create_conversation.return_value = {"id": CONV}

    mock_run.return_value = {
        "ok": False,
        "error": "Alcanzaste el límite de imágenes. Recarga desde $10 para continuar.",
        "code": "needs_recharge",
        "url": None,
    }

    with patch("app.services.chat_rate_limit.check_chat_rate_limit", return_value=(True, 0)):
        with patch("app.deps.plan_access.chat_message_limit", return_value=50):
            with patch("app.services.text_chat._cached_messages_today", return_value=0):
                out = send_message(
                    USER,
                    content="genera una imagen de un gato astronauta",
                    conversation_id=CONV,
                )

    assert not out.get("image")
    assert out.get("recharge_needed") is not None
    assert out["recharge_needed"]["resource"] == "image"
    mock_run.assert_called_once()
