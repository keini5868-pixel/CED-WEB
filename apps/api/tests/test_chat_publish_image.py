"""Publicación en chat de texto — resolución de imagen sin pedir URL."""

from unittest.mock import MagicMock, patch

from app.services.publish_image_context import (
    clear_session_image,
    get_last_uploaded_image_for_session,
    has_publishable_image,
    register_text_chat_image,
    register_text_chat_image_url,
    resolve_image_for_publishing,
)
from app.services.text_chat import _is_empty_or_placeholder_response, _run_chat_tool


def test_resolve_image_without_url_uses_session():
    uid = "user-pub-1"
    cid = "conv-pub-1"
    clear_session_image(uid, cid)
    register_text_chat_image_url(uid, cid, "https://cdn.example.com/publish/abc.jpg")
    resolved = resolve_image_for_publishing(uid, cid, use_last_uploaded_image=True)
    assert resolved["ok"] is True
    assert resolved["url"] == "https://cdn.example.com/publish/abc.jpg"


def test_resolve_image_no_session_returns_error():
    uid = "user-pub-empty"
    clear_session_image(uid, "conv-x")
    resolved = resolve_image_for_publishing(uid, "conv-x", use_last_uploaded_image=True)
    assert resolved["ok"] is False
    assert resolved["error"] == "no_image_available"


@patch("app.services.publish_media.store_publish_image", return_value="https://cdn.example.com/img.jpg")
def test_register_text_chat_image_stores_for_conversation(mock_store: MagicMock):
    uid = "user-reg"
    cid = "conv-reg"
    clear_session_image(uid, cid)
    url = register_text_chat_image(uid, cid, b"\xff\xd8\xff", "image/jpeg")
    assert url == "https://cdn.example.com/img.jpg"
    assert has_publishable_image(uid, cid)
    row = get_last_uploaded_image_for_session(uid, cid)
    assert row and row["url"] == url
    mock_store.assert_called_once()


@patch("app.services.text_chat.publish_instagram")
def test_run_chat_tool_instagram_resolves_last_image(mock_publish: MagicMock):
    uid = "user-tool-ig"
    cid = "conv-tool-ig"
    clear_session_image(uid, cid)
    register_text_chat_image_url(uid, cid, "https://cdn.example.com/ig.jpg")
    mock_publish.return_value = {"ok": True, "spoken": "Publicación enviada"}

    result = _run_chat_tool(
        uid,
        "publicar_instagram",
        {"caption": "La ciudad de Charlotte", "use_last_uploaded_image": True},
        conversation_id=cid,
    )

    assert '"ok": true' in result.lower() or '"ok": True' in result
    mock_publish.assert_called_once()
    call_kwargs = mock_publish.call_args
    assert call_kwargs[0][1] == "La ciudad de Charlotte"
    assert call_kwargs[1]["image_url"] == "https://cdn.example.com/ig.jpg"


def test_empty_placeholder_response_detector():
    assert _is_empty_or_placeholder_response("...")
    assert _is_empty_or_placeholder_response("…")
    assert _is_empty_or_placeholder_response("   ")
    assert not _is_empty_or_placeholder_response(
        "¿Necesita ayuda con el título y descripción, o ya tiene su texto?"
    )
