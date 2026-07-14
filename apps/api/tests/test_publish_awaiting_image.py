"""Publicación desde chat: awaiting_image + adjunto se conecta al borrador."""

from __future__ import annotations

import json

from app.services.publish_image_context import (
    clear_publish_flow,
    get_publish_flow,
    register_text_chat_image_url,
)
from app.services.publish_text import (
    history_awaits_publish_image,
    is_image_for_publish_signal,
)
from app.services.text_publish_flow import (
    continue_publish_after_image,
    handle_publish_flow_turn,
    start_publish_flow_awaiting_image,
)


def test_image_for_publish_signal():
    assert is_image_for_publish_signal("esa imagen")
    assert is_image_for_publish_signal("esa es la imagen")
    assert is_image_for_publish_signal("Usa esta imagen para publicar")
    assert not is_image_for_publish_signal("analiza esta foto")


def test_history_awaits_publish_image():
    history = [
        {"role": "user", "content": "necesito publicar en face"},
        {
            "role": "model",
            "content": "Facebook está conectado. Suba la imagen que desea publicar.",
        },
    ]
    assert history_awaits_publish_image(history)


def test_text_only_publish_starts_awaiting_image():
    uid = "pub-await-img-1"
    cid = "conv-await-1"
    clear_publish_flow(uid, cid)

    def fake_tool(*_a, **_k):
        return json.dumps({"ok": True})

    reply = handle_publish_flow_turn(
        uid,
        cid,
        "necesito publicar en facebook",
        history=[],
        run_tool=fake_tool,
        suggest_caption=lambda *_: "",
    )
    assert reply
    assert "imagen" in reply.lower()
    flow = get_publish_flow(uid, cid)
    assert flow
    assert flow["stage"] == "awaiting_image"
    assert flow["platform"] == "facebook"


def test_upload_after_awaiting_attaches_caption():
    uid = "pub-await-img-2"
    cid = "conv-await-2"
    clear_publish_flow(uid, cid)
    start_publish_flow_awaiting_image(
        uid,
        cid,
        "publica en facebook con el texto llegó el sistema ced",
    )
    register_text_chat_image_url(uid, cid, "https://example.com/ced.jpg")
    reply = continue_publish_after_image(
        uid,
        cid,
        "Usa esta imagen para publicar",
        history=[
            {
                "role": "user",
                "content": "una imagen y un texto que diga llegó el sistema ced",
            }
        ],
    )
    assert "Imagen recibida" in reply or "Publicaré" in reply
    flow = get_publish_flow(uid, cid)
    assert flow
    assert flow["stage"] == "awaiting_confirm"
    assert "sistema ced" in (flow.get("caption_draft") or "").lower()


def test_esa_imagen_hooks_existing_upload():
    uid = "pub-await-img-3"
    cid = "conv-await-3"
    clear_publish_flow(uid, cid)
    register_text_chat_image_url(uid, cid, "https://example.com/pic.jpg")
    history = [
        {"role": "user", "content": "quiero publicar en facebook"},
        {
            "role": "model",
            "content": "Adjunte la imagen para publicar en Facebook.",
        },
    ]

    def fake_tool(*_a, **_k):
        return json.dumps({"ok": True})

    reply = handle_publish_flow_turn(
        uid,
        cid,
        "esa es la imagen",
        history=history,
        run_tool=fake_tool,
        suggest_caption=lambda *_: "",
    )
    assert reply
    assert "publicado" not in reply.lower() or "Publicaré" in reply
    flow = get_publish_flow(uid, cid)
    assert flow
    assert flow["stage"] in {"awaiting_confirm", "awaiting_caption_choice"}
