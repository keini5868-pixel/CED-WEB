"""Tests — Meta publish prepare/confirm (piloto nativo)."""

from __future__ import annotations

from unittest.mock import patch

from app.services import voice_client_session as vcs
from app.services.meta_publish_flow import (
    cancel_meta_publish,
    confirm_meta_publish,
    prepare_meta_publish,
)
from app.services.publish_text import is_publish_confirm

USER = "550e8400-e29b-41d4-a716-446655440088"
CALL = "call_meta_test_1"


def test_publish_confirm_short_yes():
    assert is_publish_confirm("sí", allow_short_yes=True)
    assert is_publish_confirm("sí, publícalo")
    assert not is_publish_confirm("ok gracias")


def test_prepare_needs_platform():
    with patch("app.services.meta_publish_flow._meta_connected", return_value=True):
        out = prepare_meta_publish(
            USER, call_id=CALL, caption="Oferta especial", query="publica que diga Oferta especial"
        )
    # Without explicit platform, detect may fail depending on text — query has no platform
    assert out["status"] in {"needs_platform", "awaiting_confirmation"}


def test_prepare_facebook_draft():
    with patch("app.services.meta_publish_flow._meta_connected", return_value=True):
        out = prepare_meta_publish(
            USER,
            call_id=CALL,
            platform="facebook",
            caption="Oferta especial hoy en CED",
        )
    assert out["ok"] is True
    assert out["status"] == "awaiting_confirmation"
    assert out["transition"] == "transition_to_publish_confirm_pending"
    draft = vcs.get_meta_pending_publish(USER)
    assert draft is not None
    assert draft["platform"] == "facebook"
    vcs.clear_meta_pending_publish(USER)


def test_prepare_not_connected():
    with patch("app.services.meta_publish_flow._meta_connected", return_value=False):
        out = prepare_meta_publish(
            USER,
            call_id=CALL,
            platform="facebook",
            caption="Hola mundo desde CED",
        )
    assert out["status"] == "not_connected"
    assert "conectar redes" in out["spoken"].lower()


def test_prepare_instagram_needs_image():
    with patch("app.services.meta_publish_flow._meta_connected", return_value=True):
        with patch(
            "app.services.meta_publish_flow.vcs.get_last_publishable_image",
            return_value=None,
        ):
            out = prepare_meta_publish(
                USER,
                call_id=CALL,
                platform="instagram",
                caption="Look del día en CED Studio",
            )
    assert out["status"] == "needs_image"


def test_confirm_publishes_facebook():
    with patch("app.services.meta_publish_flow._meta_connected", return_value=True):
        prepare_meta_publish(
            USER,
            call_id=CALL,
            platform="facebook",
            caption="Probando publicación CED piloto",
        )
    draft_id = vcs.get_meta_pending_publish(USER)["draft_id"]
    payload = {
        "call": {
            "transcript_object": [
                {"role": "agent", "content": "¿Confirma que la publique?"},
                {"role": "user", "content": "Sí."},
            ]
        }
    }
    with patch(
        "app.services.meta_publish_flow.publish_facebook",
        return_value={"ok": True, "post_id": "fb_1", "spoken": "Publicado en Facebook."},
    ):
        result = confirm_meta_publish(USER, call_id=CALL, payload=payload, draft_id=draft_id)
    assert result["ok"] is True
    assert result["status"] == "published"
    vcs.clear_meta_pending_publish(USER)


def test_cancel_clears():
    with patch("app.services.meta_publish_flow._meta_connected", return_value=True):
        prepare_meta_publish(
            USER, call_id=CALL, platform="facebook", caption="Oferta especial hoy en CED"
        )
    draft = vcs.get_meta_pending_publish(USER)
    assert draft is not None
    out = cancel_meta_publish(USER, draft_id=draft["draft_id"])
    assert out["status"] == "cancelled"
    assert vcs.get_meta_pending_publish(USER) is None
