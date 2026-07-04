"""Integration — POST /v1/chat/send-with-image (creativo con imagen adjunta)."""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


USER_TEXT = (
    "Salud intestinal: Contribuye a mantener flora equilibrada.\n"
    "Sistema inmune: Fortalece defensas naturales.\n"
    "Y QUE ESPLIQUE SUS VBENEFICIOS USANDO ESTA IMEGENE DE REFERENCIA DEL PRODUCTO EN EL FONDO"
)


@pytest.fixture
def client():
    app = create_app()
    app.dependency_overrides[__import__("app.deps.auth", fromlist=["require_user_id"]).require_user_id] = (
        lambda: "user-test-1"
    )
    return TestClient(app)


def _mock_conversation_flow(mock_supabase: MagicMock) -> None:
    conv_id = "conv-test-1"
    mock_supabase.get_profile.return_value = {"email": "user@test.com", "role": "user"}
    mock_supabase.get_subscription.return_value = {"plan_id": "elite"}
    mock_supabase.get_conversation.return_value = {"id": conv_id, "channel": "text"}
    mock_supabase.get_conversation_messages.return_value = [
        {
            "role": "model",
            "content": (
                "FitLine Basics es un suplemento.\n"
                "Salud intestinal: flora equilibrada.\n"
                "Sistema inmune: defensas naturales."
            ),
        },
    ]
    mock_supabase.create_conversation.return_value = {"id": conv_id}
    mock_supabase.append_message.return_value = None


@patch("app.services.text_chat.supabase_db")
@patch("app.services.publish_media.store_publish_image", return_value="https://api.example.com/v1/media/publish/x.jpg")
@patch("app.services.text_chat._generate_chat_image_with_reference")
def test_send_with_image_creative_attachment_returns_200(
    mock_gen: MagicMock,
    _mock_store: MagicMock,
    mock_supabase: MagicMock,
    client: TestClient,
):
    _mock_conversation_flow(mock_supabase)
    mock_gen.return_value = {
        "ok": True,
        "url": "/api/ced/media/publish/generated.jpg",
        "quality": "standard",
    }

    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xdb\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    files = {"image": ("product.png", io.BytesIO(png_bytes), "image/png")}
    data = {"content": USER_TEXT, "conversation_id": "conv-test-1"}

    with patch("app.services.chat_rate_limit.check_chat_rate_limit", return_value=(True, 0)):
        with patch("app.deps.plan_access.chat_message_limit", return_value=-1):
            res = client.post("/v1/chat/send-with-image", data=data, files=files)

    assert res.status_code == 200, res.text
    body = res.json()
    assert body.get("reply")
    assert body.get("image", {}).get("url")
    mock_gen.assert_called_once()


@patch("app.services.text_chat.supabase_db")
@patch("app.services.publish_media.store_publish_image", return_value="https://api.example.com/v1/media/publish/x.jpg")
@patch("app.services.text_chat._generate_chat_image_with_reference")
def test_send_with_image_route_never_returns_500_on_gen_failure(
    mock_gen: MagicMock,
    _mock_store: MagicMock,
    mock_supabase: MagicMock,
    client: TestClient,
):
    _mock_conversation_flow(mock_supabase)
    mock_gen.return_value = {"ok": False, "error": "Gemini no devolvió imagen", "code": "gemini_error"}

    png_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"
    files = {"image": ("product.jpg", io.BytesIO(png_bytes), "image/jpeg")}
    data = {"content": USER_TEXT, "conversation_id": "conv-test-1"}

    with patch("app.services.chat_rate_limit.check_chat_rate_limit", return_value=(True, 0)):
        with patch("app.deps.plan_access.chat_message_limit", return_value=-1):
            res = client.post("/v1/chat/send-with-image", data=data, files=files)

    assert res.status_code == 200, res.text
    assert "No pude generar" in res.json().get("reply", "")
