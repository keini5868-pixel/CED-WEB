"""Trending topics para carrusel HUD."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.config import get_settings
from app.services import supabase_db

logger = logging.getLogger(__name__)

_CACHE: dict[str, Any] = {"at": 0.0, "lines": None}
TTL = 3600


def _tavily_trends(niche: str | None) -> list[str]:
    settings = get_settings()
    key = settings.tavily_api_key.strip()
    if not key:
        return []

    topic = niche or "inteligencia artificial marketing digital"
    payload = {
        "api_key": key,
        "query": f"tendencias hashtags {topic} esta semana",
        "max_results": 3,
        "include_answer": True,
    }
    try:
        with httpx.Client(timeout=12.0) as client:
            res = client.post("https://api.tavily.com/search", json=payload)
        if res.status_code != 200:
            return []
        data = res.json()
        answer = str(data.get("answer") or "").strip()
        if answer:
            return [answer[:72]]
        titles = [
            str(r.get("title") or "")[:40]
            for r in (data.get("results") or [])[:3]
            if r.get("title")
        ]
        return titles
    except Exception as exc:  # noqa: BLE001
        logger.warning("[HUD:TRENDING] %s", exc)
        return []


def fetch_trending_card(user_id: str) -> dict[str, Any]:
    now = time.time()
    if _CACHE.get("lines") and now - float(_CACHE.get("at") or 0) < TTL:
        return {"lines": _CACHE["lines"], "footer": "Tavily · cache 1 h"}

    profile = supabase_db.get_profile(user_id)
    niche = (profile or {}).get("niche") or (profile or {}).get("news_keywords")

    hits = _tavily_trends(str(niche) if niche else None)
    if hits:
        if len(hits) == 1:
            lines = [hits[0], "Trending en tu nicho"]
        else:
            lines = [
                " · ".join(f"{i + 1}. {t}" for i, t in enumerate(hits[:3])),
                "Subiendo esta semana",
            ]
    else:
        lines = [
            "1. #ia  2. #automation  3. #jarvis",
            "Conecta Tavily para trends en vivo",
        ]

    _CACHE["at"] = now
    _CACHE["lines"] = lines
    return {"lines": lines, "footer": "Tavily · trends"}
