"""E2E simulation: IG prepare → UI upload → attach → confirm."""
from __future__ import annotations

from unittest.mock import patch

from app.services import voice_client_session as vcs
from app.services.meta_publish_flow import (
    attach_image_to_awaiting_meta_draft,
    confirm_meta_publish,
    prepare_meta_publish,
)
from app.services.publish_media import find_latest_publish_media_url

PNG = bytes(
    [
        0x89,
        0x50,
        0x4E,
        0x47,
        0x0D,
        0x0A,
        0x1A,
        0x0A,
        0x00,
        0x00,
        0x00,
        0x0D,
        0x49,
        0x48,
        0x44,
        0x52,
        0x00,
        0x00,
        0x00,
        0x01,
        0x00,
        0x00,
        0x00,
        0x01,
        0x08,
        0x02,
        0x00,
        0x00,
        0x00,
        0x90,
        0x77,
        0x53,
        0xDE,
        0x00,
        0x00,
        0x00,
        0x0C,
        0x49,
        0x44,
        0x41,
        0x54,
        0x08,
        0xD7,
        0x63,
        0xF8,
        0xCF,
        0xC0,
        0x00,
        0x00,
        0x00,
        0x03,
        0x00,
        0x01,
        0x00,
        0x05,
        0xFE,
        0xD4,
        0xEF,
        0x00,
        0x00,
        0x00,
        0x00,
        0x49,
        0x45,
        0x4E,
        0x44,
        0xAE,
        0x42,
        0x60,
        0x82,
    ]
)

USER = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
CALL = "call_ig_e2e"

vcs.clear_meta_pending_publish(USER)
vcs.clear_last_publishable_image(USER)

with patch("app.services.meta_publish_flow._meta_connected", return_value=True):
    out1 = prepare_meta_publish(
        USER, call_id=CALL, platform="instagram", caption="Probe IG UI upload CED v18"
    )
print("STEP1", out1["status"], out1.get("draft_id"))
assert out1["status"] == "needs_image"
assert vcs.get_meta_pending_publish(USER)["status"] == "awaiting_image"

public = vcs.set_last_publishable_image_from_bytes(
    USER, PNG, "image/png", filename="probe.png"
)
print("STEP2 uploaded", public)
assert find_latest_publish_media_url(USER)

attached = attach_image_to_awaiting_meta_draft(USER, public, filename="probe.png")
print("STEP3 attach", attached and attached["status"])
assert attached and attached["status"] == "awaiting_confirmation"
assert vcs.get_meta_pending_publish(USER)["image_url"] == public

with patch("app.services.meta_publish_flow._meta_connected", return_value=True):
    out2 = prepare_meta_publish(
        USER, call_id=CALL, platform="instagram", caption="Probe IG UI upload CED v18"
    )
print("STEP4 re-prepare", out2["status"], "has_image", out2.get("has_image"))
assert out2["status"] == "awaiting_confirmation"
assert out2.get("has_image") is True

payload = {
    "call": {
        "transcript_object": [
            {"role": "agent", "content": "¿Confirma?"},
            {"role": "user", "content": "Sí, te confirmo"},
        ]
    }
}
seen: dict = {}


def fake_ig(user_id, caption, *, image_url=None, image_data=None):
    seen["image_url"] = image_url
    seen["caption"] = caption
    return {"ok": True, "media_id": "ig_probe", "spoken": "Publicado."}


with patch("app.services.meta_publish_flow.publish_instagram", side_effect=fake_ig):
    out3 = confirm_meta_publish(
        USER, call_id=CALL, payload=payload, draft_id=out2["draft_id"]
    )
print("STEP5 confirm", out3["status"], "image_passed", seen.get("image_url"))
assert out3["status"] == "published"
assert seen["image_url"] == public
print("E2E OK")
vcs.clear_meta_pending_publish(USER)
vcs.clear_last_publishable_image(USER)
