"""Publicación multi-plataforma — caption e imagen."""

import json

from app.services.publish_image_context import (
    begin_publish_flow,
    clear_publish_flow,
    get_last_uploaded_image_for_session,
    has_publishable_image,
    register_text_chat_image_url,
)
from app.services.publish_text import (
    extract_caption_from_history,
    extract_initial_publish_caption,
    extract_caption_from_turn,
    is_deictic_caption_reference,
)
from app.services.text_publish_flow import handle_publish_flow_turn, start_publish_flow_from_image


def test_extract_description_on_first_upload():
    msg = "publica esta imagen con esta descricion fitline a llegado"
    cap = extract_initial_publish_caption(msg, platform="facebook")
    assert cap == "fitline a llegado"


def test_deictic_reference_uses_history_not_literal():
    history = [
        {
            "role": "user",
            "content": "publica esta imagen con esta descricion fitline a llegado",
        },
    ]
    assert is_deictic_caption_reference("poblicala con eso que te di")
    assert extract_caption_from_turn("poblicala con eso que te di") == ""
    assert extract_caption_from_history(history) == "fitline a llegado"


def test_publish_instagram_then_facebook_keeps_image():
    uid = "user-multi"
    cid = "conv-multi"
    clear_publish_flow(uid, cid)
    register_text_chat_image_url(uid, cid, "https://cdn.example.com/fitline.jpg")
    history = [
        {
            "role": "user",
            "content": "publica esta imagen con esta descricion fitline a llegado",
        },
    ]

    opening = start_publish_flow_from_image(uid, cid, history[0]["content"], history=history)
    assert "fitline a llegado" in opening

    ig_calls: list[dict] = []

    def fake_tool(_uid, name, payload, conversation_id=None):
        ig_calls.append({"name": name, **payload})
        return json.dumps({"ok": True})

    reply_ig = handle_publish_flow_turn(
        uid,
        cid,
        "poblicala con eso que te di",
        history=history,
        run_tool=fake_tool,
        suggest_caption=lambda *_: "fallback",
    )
    assert reply_ig
    assert "fitline a llegado" in reply_ig
    assert "poblicala" not in reply_ig.lower()

    reply_send = handle_publish_flow_turn(
        uid,
        cid,
        "enviar",
        history=history + [{"role": "user", "content": "poblicala con eso que te di"}],
        run_tool=fake_tool,
        suggest_caption=lambda *_: "fallback",
    )
    assert reply_send and "instagram" in reply_send.lower()
    assert ig_calls and ig_calls[0]["name"] == "publicar_instagram"
    assert ig_calls[0]["caption"] == "fitline a llegado"
    assert has_publishable_image(uid, cid)

    fb_calls: list[dict] = []

    def fake_tool_fb(_uid, name, payload, conversation_id=None):
        fb_calls.append({"name": name, **payload})
        return json.dumps({"ok": True})

    reply_fb = handle_publish_flow_turn(
        uid,
        cid,
        "envia la publicacion a facebook",
        history=history,
        run_tool=fake_tool_fb,
        suggest_caption=lambda *_: "fallback",
    )
    assert reply_fb
    assert "fitline a llegado" in reply_fb

    reply_fb_confirm = handle_publish_flow_turn(
        uid,
        cid,
        "si envia",
        history=history,
        run_tool=fake_tool_fb,
        suggest_caption=lambda *_: "fallback",
    )
    assert reply_fb_confirm and "facebook" in reply_fb_confirm.lower()
    assert fb_calls and fb_calls[-1]["name"] == "publicar_facebook"
    assert fb_calls[-1]["message"] == "fitline a llegado"
    assert get_last_uploaded_image_for_session(uid, cid)
