"""Imágenes de historial persisten en DB, no solo en disco de Railway."""

from __future__ import annotations

from unittest.mock import patch

from app.services.publish_media import media_file_path, store_publish_image_for_client


def test_store_publish_image_saves_remote_blob(tmp_path, monkeypatch):
    from app.services import publish_media

    monkeypatch.setattr(publish_media, "_MEDIA_DIR", tmp_path)
    with patch("app.services.supabase_db.save_image_blob", return_value=True) as save:
        url = store_publish_image_for_client(
            "550e8400-e29b-41d4-a716-446655440000",
            b"\x89PNG",
            "image/png",
        )
    assert "/api/ced/media/publish/" in url
    assert save.called
    file_name = save.call_args.kwargs["file_name"]
    assert (tmp_path / file_name).is_file()


def test_media_file_path_hydrates_from_blob(tmp_path, monkeypatch):
    from app.services import publish_media

    monkeypatch.setattr(publish_media, "_MEDIA_DIR", tmp_path)
    name = "550e8400_" + ("ab" * 16) + ".png"
    with patch(
        "app.services.supabase_db.get_image_blob",
        return_value=(b"pngbytes", "image/png"),
    ):
        path = media_file_path(name)
    assert path is not None
    assert path.read_bytes() == b"pngbytes"


def test_promised_search_detects_desea_que_busque():
    from app.services.text_chat import _promised_web_search_without_tool

    assert _promised_web_search_without_tool("¿Desea que lo busque en internet?")
