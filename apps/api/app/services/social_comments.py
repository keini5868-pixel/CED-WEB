"""Lectura de comentarios recientes en Facebook e Instagram (Meta Graph)."""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from app.config import get_settings
from app.services import supabase_db
from app.services.prospection import _score_comment

logger = logging.getLogger(__name__)

LEAD_HINT = re.compile(
    r"\b(info|informaci[oó]n|precio|precios|cu[aá]nto|cuesta|interesad[oa]|"
    r"dm|mensaje|contacto|whatsapp|comprar|quiero|necesito|urgente)\b",
    re.IGNORECASE,
)


from app.services.user_address import _sanitize_honorific


def _honorific_from_profile(user_id: str) -> str:
    profile = supabase_db.get_profile(user_id) or {}
    gender = str(profile.get("gender") or "").strip().lower()
    preferred = str(profile.get("preferred_address") or "").strip()
    return _sanitize_honorific(preferred or "", gender)


def _fetch_ig_comments(
    client: httpx.Client,
    *,
    ig_id: str,
    token: str,
    api_version: str,
    posts_limit: int,
    comments_limit: int,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    media_res = client.get(
        f"https://graph.facebook.com/{api_version}/{ig_id}/media",
        params={
            "fields": "id,caption,timestamp",
            "limit": posts_limit,
            "access_token": token,
        },
    )
    media_items = (media_res.json().get("data") or [])[:posts_limit]
    for media in media_items:
        mid = media.get("id")
        if not mid:
            continue
        comments_res = client.get(
            f"https://graph.facebook.com/{api_version}/{mid}/comments",
            params={
                "fields": "id,text,username,timestamp",
                "limit": comments_limit,
                "access_token": token,
            },
        )
        for comment in comments_res.json().get("data") or []:
            text = str(comment.get("text") or "").strip()
            if not text:
                continue
            username = str(comment.get("username") or "usuario")
            score, is_hot, intent = _score_comment(text)
            out.append(
                {
                    "platform": "instagram",
                    "username": username,
                    "text": text[:280],
                    "score": score,
                    "is_hot": is_hot or bool(LEAD_HINT.search(text)),
                    "intent": intent,
                }
            )
    return out


def _fetch_fb_comments(
    client: httpx.Client,
    *,
    page_id: str,
    token: str,
    api_version: str,
    posts_limit: int,
    comments_limit: int,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    posts_res = client.get(
        f"https://graph.facebook.com/{api_version}/{page_id}/posts",
        params={
            "fields": "id,message,created_time",
            "limit": posts_limit,
            "access_token": token,
        },
    )
    for post in (posts_res.json().get("data") or [])[:posts_limit]:
        pid = post.get("id")
        if not pid:
            continue
        comments_res = client.get(
            f"https://graph.facebook.com/{api_version}/{pid}/comments",
            params={
                "fields": "id,message,from,created_time",
                "limit": comments_limit,
                "access_token": token,
            },
        )
        for comment in comments_res.json().get("data") or []:
            text = str(comment.get("message") or "").strip()
            if not text:
                continue
            author = (comment.get("from") or {}).get("name") or "usuario"
            score, is_hot, intent = _score_comment(text)
            out.append(
                {
                    "platform": "facebook",
                    "username": author,
                    "text": text[:280],
                    "score": score,
                    "is_hot": is_hot or bool(LEAD_HINT.search(text)),
                    "intent": intent,
                }
            )
    return out


def _build_spoken(comments: list[dict[str, Any]], honorific: str) -> str:
    if not comments:
        return f"{honorific}, no tiene comentarios recientes en sus publicaciones."

    hot = [c for c in comments if c.get("is_hot")]
    total = len(comments)

    if hot:
        best = max(hot, key=lambda c: int(c.get("score") or 0))
        user = best.get("username") or "alguien"
        text = str(best.get("text") or "")[:120]
        intent = str(best.get("intent") or "interés comercial")
        platform = "Instagram" if best.get("platform") == "instagram" else "Facebook"
        return (
            f"{honorific}, hay {total} comentario{'s' if total != 1 else ''} recientes. "
            f"Hay uno caliente en {platform} de {user}: «{text}». "
            f"Posible cliente, parece {intent}."
        )

    sample = comments[0]
    user = sample.get("username") or "alguien"
    text = str(sample.get("text") or "")[:100]
    extra = f" y {total - 1} más" if total > 1 else ""
    return (
        f"{honorific}, hay {total} comentario{'s' if total != 1 else ''} recientes. "
        f"El último es de {user}: \"{text}\"{extra}."
    )


def fetch_social_comments(
    user_id: str,
    *,
    platform: str = "both",
    posts_limit: int = 2,
    comments_limit: int = 15,
) -> dict[str, Any]:
    """Lee comentarios recientes de IG y/o FB para respuesta en voz."""
    conn = supabase_db.get_meta_connection(user_id)
    honorific = _honorific_from_profile(user_id)
    if not conn or not conn.get("access_token"):
        return {
            "ok": False,
            "error": "Meta no conectado",
            "spoken": f"{honorific}, Meta no está conectado. Conecte sus redes en el panel.",
        }

    token = str(conn["access_token"])
    api_version = get_settings().meta_api_version.strip() or "v21.0"
    plat = (platform or "both").strip().lower()
    comments: list[dict[str, Any]] = []

    try:
        with httpx.Client(timeout=20.0) as client:
            if plat in ("both", "instagram", "ig"):
                ig_id = conn.get("ig_user_id")
                if ig_id:
                    comments.extend(
                        _fetch_ig_comments(
                            client,
                            ig_id=str(ig_id),
                            token=token,
                            api_version=api_version,
                            posts_limit=posts_limit,
                            comments_limit=comments_limit,
                        )
                    )
            if plat in ("both", "facebook", "fb"):
                page_id = conn.get("page_id")
                if page_id:
                    comments.extend(
                        _fetch_fb_comments(
                            client,
                            page_id=str(page_id),
                            token=token,
                            api_version=api_version,
                            posts_limit=posts_limit,
                            comments_limit=comments_limit,
                        )
                    )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[SOCIAL_COMMENTS] %s", exc)
        return {
            "ok": False,
            "error": str(exc),
            "spoken": f"{honorific}, no pude leer los comentarios en este momento.",
        }

    spoken = _build_spoken(comments, honorific)
    return {
        "ok": True,
        "count": len(comments),
        "hot_count": sum(1 for c in comments if c.get("is_hot")),
        "comments": comments[:20],
        "spoken": spoken[:480],
    }
