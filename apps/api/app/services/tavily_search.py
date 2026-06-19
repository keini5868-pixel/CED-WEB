"""Búsqueda Tavily compartida — paneles HUD, voz y visión."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

TAVILY_URL = "https://api.tavily.com/search"


def tavily_raw_search(
    query: str,
    *,
    max_results: int = 5,
    include_domains: list[str] | None = None,
    search_depth: str = "basic",
) -> dict[str, Any]:
    """Respuesta completa Tavily: answer, results, response_time."""
    settings = get_settings()
    key = settings.tavily_api_key.strip()
    if not key:
        return {"query": query, "answer": None, "results": [], "response_time": 0}

    payload: dict[str, Any] = {
        "api_key": key,
        "query": query,
        "max_results": max_results,
        "include_answer": True,
        "search_depth": search_depth,
    }
    if include_domains:
        payload["include_domains"] = include_domains

    try:
        with httpx.Client(timeout=10.0) as client:
            res = client.post(TAVILY_URL, json=payload)
        if res.status_code != 200:
            logger.warning("[TAVILY] status=%s body=%s", res.status_code, res.text[:200])
            return {"query": query, "answer": None, "results": [], "response_time": 0}
        return res.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[TAVILY] %s", exc)
        return {"query": query, "answer": None, "results": [], "response_time": 0}


def tavily_answer(query: str, *, max_results: int = 5) -> str:
    """Campo `answer` de Tavily — ideal para voz (ej. búsqueda AMD)."""
    data = tavily_raw_search(query, max_results=max_results)
    answer = data.get("answer")
    if answer and isinstance(answer, str) and len(answer.strip()) >= 20:
        return answer.strip()
    for row in data.get("results") or []:
        content = str(row.get("content") or "").strip()
        if len(content) >= 40:
            return content[:400]
    return ""


def tavily_search(
    query: str,
    *,
    max_results: int = 5,
    include_domains: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Lista de resultados — answer como primer item si existe."""
    data = tavily_raw_search(query, max_results=max_results, include_domains=include_domains)
    rows = list(data.get("results") or [])
    answer = data.get("answer")
    if answer and isinstance(answer, str):
        rows.insert(
            0,
            {
                "title": "Resumen Tavily",
                "content": answer,
                "url": "",
                "score": 1.0,
            },
        )
    return rows


def tavily_voice_snippet(
    query: str,
    *,
    kind: str = "general",
    max_chars: int | None = None,
) -> str:
    """Texto hablable — prioriza `answer` de Tavily."""
    if max_chars is None:
        from app.services.voice_spoken import VOICE_NEWS_MAX_CHARS, fit_voice_spoken

        max_chars = VOICE_NEWS_MAX_CHARS if kind == "news" else 720
    else:
        from app.services.voice_spoken import fit_voice_spoken

    q = (query or "").strip()
    if not q:
        return ""

    if kind == "weather":
        search_q = f"clima tiempo actual hoy {q}"
    elif kind == "news":
        search_q = f"noticias de hoy {q}"
    else:
        search_q = q

    answer = tavily_answer(search_q, max_results=5)
    if answer:
        return fit_voice_spoken(answer, max_chars=max_chars)

    answer = tavily_answer(q, max_results=5)
    if answer:
        return fit_voice_spoken(answer, max_chars=max_chars)

    rows = tavily_search(search_q, max_results=5)
    if not rows:
        rows = tavily_search(q, max_results=5)
    for row in rows:
        text = str(row.get("content") or row.get("snippet") or "").strip()
        if len(text) >= 30:
            return fit_voice_spoken(text, max_chars=max_chars)
    if rows:
        title = str(rows[0].get("title") or "").strip()
        return fit_voice_spoken(title, max_chars=max_chars) if title else ""
    return ""
