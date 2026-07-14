"""Confirmación de publicación no debe ir por SSE sin tools (evita «Un momento…» vacío)."""

from __future__ import annotations

import json

from app.services.publish_image_context import (
    begin_publish_flow,
    clear_publish_flow,
    register_text_chat_image_url,
)
from app.services.publish_text import is_publish_confirm
from app.services.text_chat import (
    _can_stream_chat_text,
    _publish_flow_requires_blocking,
)
from app.services.text_publish_flow import handle_publish_flow_turn


def test_te_confirmo_is_publish_confirm():
    assert is_publish_confirm("te confirmo.")
    assert is_publish_confirm("Sí, te confirmo")
    assert is_publish_confirm("confirmo")


def test_confirm_forces_blocking_chat_path():
    uid = "confirm-stream-user"
    cid = "confirm-stream-conv"
    clear_publish_flow(uid, cid)
    begin_publish_flow(
        uid,
        cid,
        platform="facebook",
        caption_draft="CED ha llegado",
        stage="awaiting_confirm",
    )
    register_text_chat_image_url(uid, cid, "https://example.com/ced.jpg")

    assert _publish_flow_requires_blocking(uid, cid, "te confirmo.") is True
    assert _can_stream_chat_text("te confirmo.", user_id=uid, conversation_id=cid) is False
    assert _can_stream_chat_text("sí", user_id=uid, conversation_id=cid) is False

    clear_publish_flow(uid, cid)


def test_confirm_executes_publish_tool():
    uid = "confirm-exec-user"
    cid = "confirm-exec-conv"
    clear_publish_flow(uid, cid)
    begin_publish_flow(
        uid,
        cid,
        platform="facebook",
        caption_draft="CED ha llegado",
        stage="awaiting_confirm",
    )
    register_text_chat_image_url(uid, cid, "https://example.com/ced.jpg")

    calls: list[dict] = []

    def fake_tool(_uid, name, payload, conversation_id=None):
        calls.append({"name": name, **payload})
        return json.dumps({"ok": True, "id": "fb_post_1"})

    reply = handle_publish_flow_turn(
        uid,
        cid,
        "te confirmo.",
        history=[],
        run_tool=fake_tool,
        suggest_caption=lambda *_: "",
    )
    assert reply
    assert "Publicación enviada" in reply
    assert "Listo" in reply
    assert calls and calls[0]["name"] == "publicar_facebook"
    assert calls[0].get("message") == "CED ha llegado"
