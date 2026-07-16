"""Búsqueda de videos en YouTube — Data API v3 con API key (sin OAuth)."""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import Any

import httpx

logger = logging.getLogger(__name__)

YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_SEARCH_TIMEOUT_SEC = 8.0
YOUTUBE_SEARCH_MAX_RESULTS = 8

# Umbrales de ranking: por debajo → pedir confirmación en vez de reproducir a ciegas.
_MIN_CONFIDENT_SCORE = 0.42
_AMBIGUOUS_GAP = 0.08

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_TOKEN_RE = re.compile(r"[a-z0-9áéíóúüñ]+", re.I)
_STOPWORDS = frozenset(
    {
        "el",
        "la",
        "los",
        "las",
        "de",
        "del",
        "un",
        "una",
        "y",
        "o",
        "en",
        "por",
        "para",
        "con",
        "a",
        "al",
        "the",
        "of",
        "and",
        "official",
        "video",
        "lyrics",
        "letra",
        "audio",
        "hd",
        "mv",
        "music",
        "vevo",
        "topic",
    }
)


class YouTubeSearchError(Exception):
    """Error de búsqueda YouTube con código estable para el caller.

    Códigos: missing_api_key, timeout, http_error, invalid_response.
    """

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


def is_valid_video_id(video_id: str) -> bool:
    return bool(_VIDEO_ID_RE.match((video_id or "").strip()))


def _normalize_text(text: str) -> str:
    raw = unicodedata.normalize("NFKD", (text or "").lower())
    return "".join(ch for ch in raw if not unicodedata.combining(ch))


def _query_tokens(query: str) -> list[str]:
    tokens = [
        t
        for t in _TOKEN_RE.findall(_normalize_text(query))
        if t and t not in _STOPWORDS and len(t) > 1
    ]
    # Conservar orden y unicidad
    seen: set[str] = set()
    out: list[str] = []
    for t in tokens:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _item_to_video(item: dict[str, Any]) -> dict[str, str] | None:
    vid = str(((item.get("id") or {}).get("videoId")) or "").strip()
    if not is_valid_video_id(vid):
        return None
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


def score_youtube_candidate(query: str, video: dict[str, str]) -> float:
    """Puntuación 0–1: overlap de tokens query↔título/canal + bonus oficial."""
    q_tokens = _query_tokens(query)
    if not q_tokens:
        return 0.0
    title_n = _normalize_text(video.get("title") or "")
    channel_n = _normalize_text(video.get("channel_title") or "")
    haystack = f"{title_n} {channel_n}"
    hits = sum(1 for t in q_tokens if t in haystack)
    base = hits / len(q_tokens)

    # Bonus si el título contiene la frase completa (sin stopwords unidas).
    phrase = " ".join(q_tokens)
    if phrase and phrase in title_n:
        base = min(1.0, base + 0.25)

    # Preferir canales oficiales / Topic / VEVO cuando el match es decente.
    if base >= 0.35 and (
        "vevo" in channel_n
        or channel_n.endswith(" - topic")
        or "official" in title_n
        or "oficial" in title_n
    ):
        base = min(1.0, base + 0.12)

    # Penalizar covers/karaoke/live remix cuando el usuario no los pidió.
    q_join = " ".join(q_tokens)
    if "cover" not in q_join and "karaoke" not in q_join:
        if any(w in title_n for w in ("cover", "karaoke", "remix", "nightcore")):
            base = max(0.0, base - 0.18)

    return round(base, 4)


def rank_youtube_candidates(
    query: str,
    items: list[Any],
) -> list[dict[str, Any]]:
    """Ordena candidatos por score descendente."""
    ranked: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        video = _item_to_video(item)
        if not video:
            continue
        score = score_youtube_candidate(query, video)
        ranked.append({**video, "score": score})
    ranked.sort(key=lambda row: float(row.get("score") or 0), reverse=True)
    return ranked


def _pick_from_ranked(
    ranked: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Elige ganador o marca ambigüedad.

    Returns:
        dict con campos de video + optional ambiguous=True y candidates.
        None si no hay resultados.
    """
    if not ranked:
        return None
    top = ranked[0]
    top_score = float(top.get("score") or 0)
    second = float(ranked[1].get("score") or 0) if len(ranked) > 1 else 0.0
    gap = top_score - second

    # Limpiar score interno del payload principal.
    def _clean(row: dict[str, Any]) -> dict[str, str]:
        return {
            "video_id": str(row.get("video_id") or ""),
            "title": str(row.get("title") or ""),
            "channel_title": str(row.get("channel_title") or ""),
            "thumbnail_url": str(row.get("thumbnail_url") or ""),
        }

    winner = _clean(top)
    ambiguous = top_score < _MIN_CONFIDENT_SCORE or (
        len(ranked) > 1 and gap < _AMBIGUOUS_GAP and second >= 0.28
    )
    out: dict[str, Any] = {**winner, "score": top_score, "ambiguous": ambiguous}
    if ambiguous:
        out["candidates"] = [_clean(r) for r in ranked[:3]]
    return out


def _extract_video(items: list[Any]) -> dict[str, str] | None:
    """Compat: primer video válido (sin ranking). Preferir rank_youtube_candidates."""
    for item in items:
        if not isinstance(item, dict):
            continue
        video = _item_to_video(item)
        if video:
            return video
    return None


def search_youtube_video(
    query: str,
    *,
    api_key: str | None = None,
    timeout: float = YOUTUBE_SEARCH_TIMEOUT_SEC,
    transport: httpx.BaseTransport | None = None,
    max_results: int = YOUTUBE_SEARCH_MAX_RESULTS,
    require_confident: bool = False,
) -> dict[str, Any] | None:
    """Busca el mejor video embebible para `query`.

    Returns:
        dict {video_id, title, channel_title, thumbnail_url, score?, ambiguous?}
        o None si no hay resultados. NUNCA inventa resultados.

        Si `require_confident` y el top es ambiguo, igual devuelve el top con
        ambiguous=True para que el caller pida confirmación.

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
        "maxResults": max(1, min(int(max_results), 10)),
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

    ranked = rank_youtube_candidates(q, items)
    picked = _pick_from_ranked(ranked)
    if not picked:
        return None

    logger.info(
        "[YOUTUBE] pick query=%r title=%r score=%.2f ambiguous=%s",
        q[:60],
        str(picked.get("title") or "")[:60],
        float(picked.get("score") or 0),
        bool(picked.get("ambiguous")),
    )
    # require_confident no descarta; el caller decide si confirma.
    _ = require_confident
    return picked
