"""Flujo ayuda caption publicación."""

import json

from app.services.publish_image_context import (
    get_publish_flow,
    has_publishable_image,
    register_text_chat_image_url,
)
from app.services.publish_text import is_publish_help_request, is_social_publish_intent
from app.services.text_publish_flow import handle_publish_flow_turn, start_publish_flow_from_image


def test_publish_help_caption_does_not_crash():
    uid = "user-test"
    conv = "conv-test"
    register_text_chat_image_url(uid, conv, "https://example.com/img.jpg")
    history = [
        {"role": "user", "content": "genera creativo fitline"},
        {"role": "model", "content": "Creativo FitLine Basics"},
    ]
    msg = "publica esta imagen en facebook y ponle un titulo creativo"
    assert is_social_publish_intent(msg)
    assert has_publishable_image(uid, conv)
    opening = start_publish_flow_from_image(uid, conv, msg)
    assert "Facebook" in opening or "facebook" in opening.lower()
    assert get_publish_flow(uid, conv)

    help_msg = "ayudame con el titulo y la descripcion"
    assert is_publish_help_request(help_msg)

    def fake_tool(*_args, **_kwargs):
        return json.dumps({"ok": True})

    def fake_suggest(_platform, _user_text, _history):
        return "FitLine Basics: bienestar digestivo diario. #FitLine #Salud #CED"

    reply = handle_publish_flow_turn(
        uid,
        conv,
        help_msg,
        history=history,
        run_tool=fake_tool,
        suggest_caption=fake_suggest,
    )
    assert reply
    assert "FitLine Basics" in reply or "propongo" in reply.lower()
