"""Instagram stats para carrusel HUD."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings
from app.services import supabase_db

logger = logging.getLogger(__name__)


def _refresh_from_graph(conn: dict[str, Any]) -> dict[str, Any]:
    token = str(conn.get("access_token") or "").strip()
    ig_id = str(conn.get("ig_user_id") or "").strip()
    if not token or not ig_id:
        return conn

    url = (
        f"https://graph.facebook.com/v21.0/{ig_id}"
        f"?fields=followers_count,media_count,username"
        f"&access_token={token}"
    )
    try:
        with httpx.Client(timeout=12.0) as client:
            res = client.get(url)
        if res.status_code != 200:
            return conn
        data = res.json()
        followers = int(data.get("followers_count") or conn.get("followers_count") or 0)
        media = int(data.get("media_count") or conn.get("media_count") or 0)
        username = data.get("username") or conn.get("ig_username")
        updated = {
            "followers_count": followers,
            "media_count": media,
            "ig_username": username,
        }
        user_id = conn.get("user_id")
        if user_id:
            supabase_db.upsert_meta_connection(str(user_id), updated)
        return {**conn, **updated}
    except Exception as exc:  # noqa: BLE001
        logger.warning("[HUD:IG] graph %s", exc)
        return conn


def fetch_instagram_card(user_id: str) -> dict[str, Any]:
    settings = get_settings()
    conn = supabase_db.get_meta_connection(user_id)

    if conn and conn.get("access_token"):
        conn = _refresh_from_graph({**conn, "user_id": user_id})
        followers = int(conn.get("followers_count") or 0)
        username = conn.get("ig_username") or "instagram"
        engagement = conn.get("engagement_rate")
        eng_line = (
            f"Engagement {float(engagement):.1f}%"
            if engagement is not None
            else f"{conn.get('media_count') or 0} publicaciones"
        )
        return {
            "lines": [
                f"@{username} · {followers:,} seguidores".replace(",", "."),
                eng_line,
            ],
            "footer": "Meta Graph · en vivo",
        }

    connect_hint = "Conecta Instagram en Ajustes"
    if settings.meta_app_id.strip():
        connect_hint = "Conectar en /dashboard → Meta OAuth"

    return {
        "lines": [
            "Sin cuenta conectada",
            connect_hint,
        ],
        "footer": "Meta Graph API",
    }
