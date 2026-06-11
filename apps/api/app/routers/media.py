"""Servir y subir imágenes temporales para publicación Meta."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.deps.auth import require_user_id
from app.services.publish_media import decode_image_data, media_file_path, store_publish_image

router = APIRouter(prefix="/v1/media", tags=["media"])

_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


class ImageUploadBody(BaseModel):
    image: str = Field(min_length=32, description="Data URL o base64 de la imagen")


@router.post("/upload")
def upload_publish_image(
    body: ImageUploadBody,
    user_id: str = Depends(require_user_id),
) -> dict:
    try:
        raw, mime = decode_image_data(body.image)
        public_url = store_publish_image(user_id, raw, mime)
        return {"ok": True, "url": public_url, "mime": mime}
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"No se pudo subir la imagen: {exc}"}


@router.get("/publish/{file_name}")
def serve_publish_media(file_name: str) -> FileResponse:
    path: Path | None = media_file_path(file_name)
    if not path:
        raise HTTPException(status_code=404, detail="Imagen no encontrada")
    ext = path.suffix.lower()
    media_type = _MIME.get(ext, "application/octet-stream")
    return FileResponse(path, media_type=media_type)
