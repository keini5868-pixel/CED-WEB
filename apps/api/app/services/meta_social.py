"""Publicación Facebook / Instagram vía conexión Meta OAuth."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings
from app.services import supabase_db
from app.services.publish_media import resolve_image_input

logger = logging.getLogger(__name__)


class MetaSocialError(RuntimeError):
    pass


def _connection(user_id: str) -> dict[str, Any]:
    conn = supabase_db.get_meta_connection(user_id)
    if not conn or not conn.get("access_token"):
        raise MetaSocialError("Instagram no conectado. Use Conectar Redes en el dashboard.")
    return conn


def publish_facebook(
    user_id: str,
    message: str,
    *,
    image_url: str | None = None,
    image_data: str | None = None,
) -> dict[str, Any]:
    text = (message or "").strip()
    if not text:
        raise MetaSocialError("El mensaje de Facebook no puede estar vacío.")

    conn = _connection(user_id)
    page_id = conn.get("page_id")
    token = str(conn["access_token"])
    api_version = get_settings().meta_api_version.strip() or "v21.0"

    public_url, image_bytes, mime = resolve_image_input(
        user_id=user_id,
        image_url=image_url,
        image_data=image_data,
    )

    with httpx.Client(timeout=30.0) as client:
        if image_bytes:
            ext = "jpg" if "jpeg" in mime else "png"
            path = f"https://graph.facebook.com/{api_version}/{page_id}/photos"
            res = client.post(
                path,
                data={"caption": text, "access_token": token},
                files={"source": (f"photo.{ext}", image_bytes, mime)},
            )
        elif public_url:
            path = f"https://graph.facebook.com/{api_version}/{page_id}/photos"
            res = client.post(
                path,
                data={"caption": text, "url": public_url, "access_token": token},
            )
        else:
            path = f"https://graph.facebook.com/{api_version}/{page_id}/feed"
            res = client.post(path, data={"message": text, "access_token": token})

        data = res.json()
        if res.status_code >= 400 or data.get("error"):
            err = data.get("error", {}).get("message") or str(data)
            raise MetaSocialError(f"Facebook: {err}")

    supabase_db.log_ced_activity(user_id, "facebook_post", detail=text[:120])
    return {"ok": True, "platform": "facebook", "post_id": data.get("id"), "spoken": "Publicado en Facebook."}


def publish_instagram(
    user_id: str,
    caption: str,
    *,
    image_url: str | None = None,
    image_data: str | None = None,
) -> dict[str, Any]:
    text = (caption or "").strip()
    if not text:
        raise MetaSocialError("El caption de Instagram no puede estar vacío.")

    public_url, _, _ = resolve_image_input(
        user_id=user_id,
        image_url=image_url,
        image_data=image_data,
    )
    if not public_url:
        raise MetaSocialError(
            "Instagram requiere una imagen. Muéstrame la foto, genera una con IA o pásame la imagen."
        )

    conn = _connection(user_id)
    ig_id = conn.get("ig_user_id")
    token = str(conn["access_token"])
    api_version = get_settings().meta_api_version.strip() or "v21.0"
    if not ig_id:
        raise MetaSocialError("Cuenta Instagram Business no vinculada.")

    with httpx.Client(timeout=30.0) as client:
        create = client.post(
            f"https://graph.facebook.com/{api_version}/{ig_id}/media",
            data={
                "caption": text,
                "image_url": public_url,
                "access_token": token,
            },
        ).json()
        creation_id = create.get("id")
        if not creation_id:
            err = create.get("error", {}).get("message") or str(create)
            raise MetaSocialError(f"Instagram: {err}")

        published = client.post(
            f"https://graph.facebook.com/{api_version}/{ig_id}/media_publish",
            data={"creation_id": creation_id, "access_token": token},
        ).json()
        if published.get("error"):
            err = published["error"].get("message") or str(published)
            raise MetaSocialError(f"Instagram: {err}")

    supabase_db.log_ced_activity(user_id, "instagram_post", detail=text[:120])
    return {
        "ok": True,
        "platform": "instagram",
        "media_id": published.get("id"),
        "spoken": "Publicado en Instagram.",
    }
