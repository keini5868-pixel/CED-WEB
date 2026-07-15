"""Búsqueda de videos en YouTube — Data API v3 con API key (sin OAuth)."""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

logger = logging.getLogger(__name__)

YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_SEARCH_TIMEOUT_SEC = 8.0

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


class YouTubeSearchError(Exception):
    """Error de búsqueda YouTube con código estable para el caller.

    Códigos: missing_api_key, timeout, http_error, invalid_response.
    """

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


def is_valid_video_id(video_id: str) -> bool:
    return bool(_VIDEO_ID_RE.match((video_id or "").strip()))


def _extract_video(items: list[Any]) -> dict[str, str] | None:
    for item in items:
        if not isinstance(item, dict):
            continue
        vid = str(((item.get("id") or {}).get("videoId")) or "").strip()
        if not is_valid_video_id(vid):
            continue
        snippet = item.get("snippet") or {}
        thumbs = snippet.get("thumbnails") or {}
        thumb = (
            (thumbs.get("medium") or {}).get("url")
            or (thumbs.get("high") or {}).get("url")
            or (thumbs.get("default") or {}).get("url")
            or ""
        )
        return {
            "video_id": vid,
            "title": str(snippet.get("title") or "").strip(),
            "channel_title": str(snippet.get("channelTitle") or "").strip(),
            "thumbnail_url": str(thumb).strip(),
        }
    return None


def search_youtube_video(
    query: str,
    *,
    api_key: str | None = None,
    timeout: float = YOUTUBE_SEARCH_TIMEOUT_SEC,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, str] | None:
    """Busca UN video público y embebible en YouTube.

    Returns:
        dict {video_id, title, channel_title, thumbnail_url} o None si no hay
        resultados reales. NUNCA inventa resultados.

    Raises:
        YouTubeSearchError: clave ausente, timeout o error HTTP/parseo.
    """
    q = (query or "").strip()
    if not q:
        return None

    if api_key is None:
        from app.config import get_settings

        api_key = get_settings().youtube_api_key
    key = (api_key or "").strip()
    if not key:
        raise YouTubeSearchError("missing_api_key")

    params = {
        "part": "snippet",
        "type": "video",
        "videoEmbeddable": "true",
        "maxResults": 1,
        "q": q,
        "key": key,
    }
    try:
        with httpx.Client(timeout=timeout, transport=transport) as client:
            response = client.get(YOUTUBE_SEARCH_URL, params=params)
            response.raise_for_status()
            data = response.json()
    except httpx.TimeoutException as exc:
        logger.warning("[YOUTUBE] búsqueda timeout query=%r", q[:80])
        raise YouTubeSearchError("timeout") from exc
    except httpx.HTTPStatusError as exc:
        # No incluir la URL en logs: contiene la API key.
        logger.warning(
            "[YOUTUBE] búsqueda HTTP %s query=%r",
            exc.response.status_code,
            q[:80],
        )
        raise YouTubeSearchError("http_error", f"HTTP {exc.response.status_code}") from exc
    except httpx.HTTPError as exc:
        logger.warning("[YOUTUBE] búsqueda falló query=%r: %s", q[:80], type(exc).__name__)
        raise YouTubeSearchError("http_error") from exc
    except ValueError as exc:  # JSON inválido
        raise YouTubeSearchError("invalid_response") from exc

    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise YouTubeSearchError("invalid_response")
    return _extract_video(items)
