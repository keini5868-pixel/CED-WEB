"""Almacenamiento temporal de imágenes para publicar en Meta (URL HTTPS pública)."""

from __future__ import annotations

import base64
import logging
import re
import time
import uuid
from pathlib import Path

from app.config import get_settings

logger = logging.getLogger(__name__)

_API_ROOT = Path(__file__).resolve().parent.parent
_MEDIA_DIR = _API_ROOT / "data" / "publish_media"

_EXT_BY_MIME = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}


def _ensure_dir() -> Path:
    _MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    return _MEDIA_DIR


def decode_image_data(image_data: str) -> tuple[bytes, str]:
    """Acepta data URL, base64 crudo o URL http(s) (descarga)."""
    raw = (image_data or "").strip()
    if not raw:
        raise ValueError("Imagen vacía")

    if raw.startswith("data:"):
        header, payload = raw.split(",", 1)
        mime = header.split(";")[0].replace("data:", "").strip() or "image/jpeg"
        return base64.b64decode(payload), mime

    if raw.startswith("http://") or raw.startswith("https://"):
        import httpx

        with httpx.Client(timeout=25.0, follow_redirects=True) as client:
            res = client.get(raw)
            res.raise_for_status()
            mime = res.headers.get("content-type", "image/jpeg").split(";")[0].strip()
            return res.content, mime or "image/jpeg"

    cleaned = re.sub(r"\s+", "", raw)
    try:
        return base64.b64decode(cleaned), "image/jpeg"
    except Exception as exc:  # noqa: BLE001
        raise ValueError("Formato de imagen no reconocido") from exc


def _save_image_file(user_id: str, image_bytes: bytes, mime: str) -> str:
    ext = _EXT_BY_MIME.get(mime.lower(), "jpg")
    file_name = f"{user_id[:8]}_{uuid.uuid4().hex}.{ext}"
    path = _ensure_dir() / file_name
    path.write_bytes(image_bytes)
    return file_name


def api_media_url(file_name: str) -> str:
    settings = get_settings()
    base = settings.api_public_url.rstrip("/")
    return f"{base}/v1/media/publish/{file_name}"


def client_media_url(file_name: str) -> str:
    return f"/api/ced/media/publish/{file_name}"


def store_publish_image(user_id: str, image_bytes: bytes, mime: str) -> str:
    """URL HTTPS pública en la API (Meta / Instagram)."""
    file_name = _save_image_file(user_id, image_bytes, mime)
    return api_media_url(file_name)


def find_latest_publish_media_url(
    user_id: str,
    *,
    max_age_sec: float = 900.0,
) -> str | None:
    """Última imagen en disco para el usuario (útil si otra réplica no tiene la sesión en memoria)."""
    uid = (user_id or "").strip()
    if not uid:
        return None
    prefix = f"{uid[:8]}_"
    try:
        root = _ensure_dir()
    except Exception:  # noqa: BLE001
        return None
    now = time.time()
    best: Path | None = None
    best_mtime = 0.0
    for path in root.glob(f"{prefix}*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if now - mtime > max_age_sec:
            continue
        if mtime > best_mtime:
            best = path
            best_mtime = mtime
    if not best:
        return None
    return api_media_url(best.name)


def store_publish_image_for_client(user_id: str, image_bytes: bytes, mime: str) -> str:
    """URL same-origin vía BFF Next.js — para mostrar en el chat."""
    file_name = _save_image_file(user_id, image_bytes, mime)
    return client_media_url(file_name)


def resolve_image_input(
    *,
    user_id: str,
    image_url: str | None = None,
    image_data: str | None = None,
) -> tuple[str | None, bytes | None, str]:
    """
    Resuelve imagen para Meta.
    Returns: (public_https_url, bytes_for_fb_upload, mime)
    """
    data = (image_data or "").strip()
    url = (image_url or "").strip()

    if data:
        raw, mime = decode_image_data(data)
        public = store_publish_image(user_id, raw, mime)
        return public, raw, mime

    if url.startswith("data:"):
        raw, mime = decode_image_data(url)
        public = store_publish_image(user_id, raw, mime)
        return public, raw, mime

    if url.startswith("http://") or url.startswith("https://"):
        return url, None, "image/jpeg"

    return None, None, "image/jpeg"


def media_file_path(file_name: str) -> Path | None:
    if not file_name or ".." in file_name or "/" in file_name or "\\" in file_name:
        return None
    path = _ensure_dir() / file_name
    return path if path.is_file() else None
