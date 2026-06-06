"""Noticias HUD — Tavily con caché + fallback Gemini grounding."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.config import get_settings
from app.services.gemini_grounded import fetch_voice_brief

logger = logging.getLogger(__name__)

NEWS_TTL_SEC = 30 * 60
_news_cache: dict[str, Any] = {"at": 0.0, "lines": None, "footer": None}


def _fetch_tavily_headline() -> dict[str, Any] | None:
    settings = get_settings()
    api_key = settings.tavily_api_key.strip()
    if not api_key:
        return None

    payload = {
        "api_key": api_key,
        "query": "noticias tecnología e inteligencia artificial hoy",
        "max_results": 1,
        "topic": "news",
        "include_answer": False,
    }
    try:
        with httpx.Client(timeout=12.0) as client:
            response = client.post("https://api.tavily.com/search", json=payload)
        if response.status_code != 200:
            logger.warning("[HUD:NEWS] tavily status=%s", response.status_code)
            return None
        data = response.json()
        results = data.get("results") or []
        if not results:
            return None
        hit = results[0]
        title = str(hit.get("title") or "").strip()
        url = str(hit.get("url") or "")
        source = url.split("/")[2] if "://" in url else "Web"
        if not title:
            return None
        headline = title[:60]
        return {
            "lines": [headline, f"{source} · reciente"],
            "footer": "Tavily · keywords en ajustes",
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("[HUD:NEWS] tavily error: %s", exc)
        return None


def _fetch_gemini_headline() -> dict[str, Any] | None:
    result = fetch_voice_brief(
        "noticia más relevante de tecnología hoy",
        kind="news",
    )
    if not result.get("ok"):
        return None
    summary = str(result.get("summary") or "").strip()
    if not summary:
        return None
    parts = [p.strip() for p in summary.replace("Señor,", "").split(".") if p.strip()]
    lines = parts[:2] if parts else [summary[:60]]
    return {
        "lines": [line[:72] for line in lines],
        "footer": "Google Search · Gemini",
    }


def fetch_hud_news_lines() -> dict[str, Any]:
    """Headline para tarjeta NEWS — caché 30 min."""
    now = time.time()
    if _news_cache.get("lines") and now - float(_news_cache.get("at") or 0) < NEWS_TTL_SEC:
        return {
            "lines": _news_cache["lines"],
            "footer": _news_cache.get("footer"),
        }

    payload = _fetch_tavily_headline() or _fetch_gemini_headline()
    if not payload:
        payload = {
            "lines": [
                "IA generativa redefine flujos de venta B2B",
                "CED · modo demo",
            ],
            "footer": "Conecta Tavily o Gemini para noticias en vivo",
        }

    _news_cache["at"] = now
    _news_cache["lines"] = payload["lines"]
    _news_cache["footer"] = payload.get("footer")
    return payload
