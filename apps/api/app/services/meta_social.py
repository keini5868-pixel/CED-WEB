"""Publicación Facebook / Instagram vía conexión Meta OAuth."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings
from app.services import supabase_db
from app.services.meta_publish_dedupe import find_duplicate_publish, record_publish
from app.services.publish_media import resolve_image_input

logger = logging.getLogger(__name__)


class MetaSocialError(RuntimeError):
    pass


def _connection(user_id: str) -> dict[str, Any]:
    conn = supabase_db.get_meta_connection(user_id)
    if not conn or not conn.get("access_token"):
        raise MetaSocialError(
            "Meta no conectado. Ve al dashboard y pulsa Conectar Redes."
        )
    return conn


def publish_facebook(
    user_id: str,
    message: str,
    *,
    image_url: str | None = None,
    image_data: str | None = None,
) -> dict[str, Any]:
    from app.services.publish_text import sanitize_publish_caption, validate_caption

    text = sanitize_publish_caption(message)
    is_valid, reason = validate_caption(text)
    if not is_valid:
        logger.warning("[PUBLISH] caption inválido FB user=%s: %s", user_id[:8], reason)
        raise MetaSocialError(
            "El texto a publicar no parece correcto. ¿Puede confirmar el texto exacto?"
        )

    dup_post_id = find_duplicate_publish(user_id, text, platform="facebook")
    if dup_post_id:
        logger.info(
            "[META:FB] dedupe=skip user=%s post_id=%s message_len=%s",
            user_id[:8],
            dup_post_id,
            len(text),
        )
        return {
            "ok": True,
            "platform": "facebook",
            "post_id": dup_post_id if dup_post_id != "dedupe" else None,
            "spoken": "Publicación enviada con éxito a Facebook, señor.",
            "dedupe": True,
        }

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
            logger.info("[META:FB] POST %s caption_len=%s has_bytes=%s", path, len(text), True)
            res = client.post(
                path,
                data={"caption": text, "access_token": token},
                files={"source": (f"photo.{ext}", image_bytes, mime)},
            )
        elif public_url:
            path = f"https://graph.facebook.com/{api_version}/{page_id}/photos"
            logger.info("[META:FB] POST %s caption_len=%s image_url=%s", path, len(text), public_url[:120])
            res = client.post(
                path,
                data={"caption": text, "url": public_url, "access_token": token},
            )
        else:
            path = f"https://graph.facebook.com/{api_version}/{page_id}/feed"
            logger.info("[META:FB] POST %s message_len=%s page_id=%s", path, len(text), page_id)
            res = client.post(path, data={"message": text, "access_token": token})

        raw_body = res.text[:800]
        logger.info("[META:FB] response status=%s body=%s", res.status_code, raw_body)
        data = res.json()
        if res.status_code >= 400 or data.get("error"):
            err = data.get("error", {}).get("message") or str(data)
            raise MetaSocialError(f"Facebook: {err}")

    post_id = data.get("id")
    record_publish(user_id, text, str(post_id) if post_id else None, platform="facebook")
    supabase_db.log_ced_activity(user_id, "facebook_post", detail=text[:120])
    return {
        "ok": True,
        "platform": "facebook",
        "post_id": post_id,
        "spoken": "Publicación enviada con éxito a Facebook, señor.",
    }


def publish_instagram(
    user_id: str,
    caption: str,
    *,
    image_url: str | None = None,
    image_data: str | None = None,
) -> dict[str, Any]:
    from app.services.publish_text import sanitize_publish_caption, validate_caption

    text = sanitize_publish_caption(caption)
    is_valid, reason = validate_caption(text)
    if not is_valid:
        logger.warning("[PUBLISH] caption inválido IG user=%s: %s", user_id[:8], reason)
        raise MetaSocialError(
            "El texto a publicar no parece correcto. ¿Puede confirmar el texto exacto?"
        )

    public_url, _, _ = resolve_image_input(
        user_id=user_id,
        image_url=image_url,
        image_data=image_data,
    )
    if not public_url:
        raise MetaSocialError(
            "Instagram requiere una imagen. Muéstrame la foto, genera una con IA o pásame la imagen."
        )

    settings = get_settings()
    public_base = settings.api_public_url.rstrip("/")
    if public_url and ("localhost" in public_url or "127.0.0.1" in public_url):
        raise MetaSocialError(
            "La URL de imagen no es accesible para Instagram. "
            "Configura API_PUBLIC_URL con tu dominio HTTPS en Railway."
        )
    if not public_base.startswith("https://"):
        logger.warning("[META:IG] API_PUBLIC_URL sin HTTPS: %s", public_base)

    conn = _connection(user_id)
    ig_id = conn.get("ig_user_id")
    token = str(conn["access_token"])
    api_version = settings.meta_api_version.strip() or "v21.0"
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
        "spoken": "Publicación enviada.",
    }
