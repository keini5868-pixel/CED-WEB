"""Adjuntos del chat de soporte — almacenamiento local en API."""

from __future__ import annotations

import uuid
from pathlib import Path

from app.config import get_settings
from app.services.publish_media import _EXT_BY_MIME, decode_image_data

_API_ROOT = Path(__file__).resolve().parent.parent
_MEDIA_DIR = _API_ROOT / "data" / "support_attachments"
_MAX_BYTES = 5 * 1024 * 1024
_ALLOWED = frozenset({"image/jpeg", "image/jpg", "image/png", "image/webp"})


def _ensure_dir() -> Path:
    _MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    return _MEDIA_DIR


def validate_support_image(image_bytes: bytes, mime: str) -> None:
    if mime.lower() not in _ALLOWED:
        raise ValueError("Solo se permiten imágenes JPEG, PNG o WebP.")
    if len(image_bytes) > _MAX_BYTES:
        raise ValueError("La imagen no puede superar 5 MB.")


def store_support_attachment(
    user_id: str,
    conversation_id: str,
    image_bytes: bytes,
    mime: str,
) -> str:
    validate_support_image(image_bytes, mime)
    ext = _EXT_BY_MIME.get(mime.lower(), "jpg")
    file_name = f"{user_id[:8]}_{conversation_id[:8]}_{uuid.uuid4().hex}.{ext}"
    path = _ensure_dir() / file_name
    path.write_bytes(image_bytes)
    return file_name


def support_attachment_api_url(file_name: str) -> str:
    settings = get_settings()
    base = settings.api_public_url.rstrip("/")
    return f"{base}/v1/support/attachments/{file_name}"


def support_attachment_client_url(file_name: str) -> str:
    return f"/api/ced/support/attachments/{file_name}"


def support_attachment_path(file_name: str) -> Path | None:
    if not file_name or ".." in file_name or "/" in file_name or "\\" in file_name:
        return None
    path = _ensure_dir() / file_name
    return path if path.is_file() else None


def decode_support_upload(raw: str | bytes, mime_hint: str | None = None) -> tuple[bytes, str]:
    if isinstance(raw, bytes):
        mime = (mime_hint or "image/jpeg").split(";")[0].strip()
        return raw, mime
    return decode_image_data(raw)
