"""Publish flow: generated image URL + caption garbage + Meta public URL."""

from __future__ import annotations

from app.services.publish_media import to_public_meta_image_url
from app.services.publish_text import (
    _is_instruction_garbage_caption,
    extract_initial_publish_caption,
    extract_user_caption_for_publish,
    is_publish_help_request,
    validate_caption,
)


def test_client_media_path_becomes_public_https(monkeypatch):
    monkeypatch.setenv("API_PUBLIC_URL", "https://ced-web-production.up.railway.app")
    from app.config import get_settings

    get_settings.cache_clear()
    url = to_public_meta_image_url("/api/ced/media/publish/24b62e5d_abc.png")
    assert url.startswith("https://")
    assert url.endswith("/v1/media/publish/24b62e5d_abc.png")
    get_settings.cache_clear()


def test_publish_instruction_typo_is_not_caption():
    msg = "publica esta imgen en intagran"
    assert extract_initial_publish_caption(msg) == ""
    assert _is_instruction_garbage_caption("esta imgen en intagran")
    assert validate_caption("esta imgen en intagran")[0] is False


def test_si_alone_is_publish_help():
    assert is_publish_help_request("si")
    assert is_publish_help_request("sí")


def test_ponle_caption_then_send():
    msg = "si ponle ced llego envia"
    cap = extract_user_caption_for_publish(msg)
    assert "ced" in cap.lower()
    assert "envia" not in cap.lower()
