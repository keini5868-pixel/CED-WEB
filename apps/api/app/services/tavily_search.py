"""Búsqueda Tavily compartida — paneles HUD, voz y visión."""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

TAVILY_URL = "https://api.tavily.com/search"
DEFAULT_MAX_RESULTS = 3

_NEWS_QUERY_HINTS = re.compile(
    r"\b(noticias?|última hora|ultima hora|breaking|hoy|ayer|esta semana)\b",
    re.I,
)
_RESEARCH_HINTS = re.compile(
    r"\b("
    r"investig(a|ación|ar)|research|análisis profundo|analisis profundo|"
    r"deep dive|estudio detallado|modo avanzado|investigación profunda"
    r")\b",
    re.I,
)


def infer_tavily_topic(query: str, *, kind: str = "general") -> str:
    """Topic Tavily: news solo si kind o query lo ameritan; general es más rápido."""
    if kind == "news":
        return "news"
    if _NEWS_QUERY_HINTS.search((query or "").strip()):
        return "news"
    return "general"


def resolve_search_depth(
    query: str,
    *,
    kind: str = "general",
    research: bool = False,
) -> str:
    """basic por defecto; advanced solo para investigación explícita."""
    if research:
        return "advanced"
    q = (query or "").strip()
    if _RESEARCH_HINTS.search(q):
        return "advanced"
    return "basic"


def tavily_raw_search(
    query: str,
    *,
    max_results: int = DEFAULT_MAX_RESULTS,
    include_domains: list[str] | None = None,
    search_depth: str | None = None,
    topic: str | None = None,
    kind: str = "general",
    research: bool = False,
    timeout_sec: float = 5.0,
) -> dict[str, Any]:
    """Respuesta completa Tavily: answer, results, response_time."""
    settings = get_settings()
    key = settings.tavily_api_key.strip()
    if not key:
        return {
            "query": query,
            "answer": None,
            "results": [],
            "response_time": 0,
            "error": "missing_tavily_key",
        }

    depth = search_depth or resolve_search_depth(query, kind=kind, research=research)
    tavily_topic = topic or infer_tavily_topic(query, kind=kind)

    payload: dict[str, Any] = {
        "api_key": key,
        "query": query,
        "max_results": max_results,
        "include_answer": True,
        "search_depth": depth,
        "topic": tavily_topic,
    }
    if include_domains:
        payload["include_domains"] = include_domains

    try:
        with httpx.Client(timeout=timeout_sec) as client:
            res = client.post(TAVILY_URL, json=payload)
        if res.status_code == 429:
            logger.warning(
                "[TAVILY] rate limit 429 query=%s",
                (query or "")[:60],
            )
            return {
                "query": query,
                "answer": None,
                "results": [],
                "response_time": 0,
                "rate_limited": True,
                "error": "rate_limited",
            }
        if res.status_code != 200:
            logger.warning("[TAVILY] status=%s body=%s", res.status_code, res.text[:200])
            return {
                "query": query,
                "answer": None,
                "results": [],
                "response_time": 0,
                "error": f"http_{res.status_code}",
            }
        data = res.json()
        logger.info(
            "[TAVILY] q=%s topic=%s depth=%s max=%s rt=%s",
            (query or "")[:60],
            tavily_topic,
            depth,
            max_results,
            data.get("response_time"),
        )
        return data
    except Exception as exc:  # noqa: BLE001
        logger.warning("[TAVILY] %s", exc)
        return {
            "query": query,
            "answer": None,
            "results": [],
            "response_time": 0,
            "error": f"exception:{type(exc).__name__}",
        }


def tavily_answer(
    query: str,
    *,
    max_results: int = DEFAULT_MAX_RESULTS,
    kind: str = "general",
    research: bool = False,
) -> str:
    """Campo `answer` de Tavily — ideal para voz (ej. búsqueda AMD)."""
    data = tavily_raw_search(
        query,
        max_results=max_results,
        kind=kind,
        research=research,
    )
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
    max_results: int = DEFAULT_MAX_RESULTS,
    include_domains: list[str] | None = None,
    search_depth: str | None = None,
    topic: str | None = None,
    kind: str = "general",
    research: bool = False,
) -> list[dict[str, Any]]:
    """Lista de resultados — answer como primer item si existe."""
    data = tavily_raw_search(
        query,
        max_results=max_results,
        include_domains=include_domains,
        search_depth=search_depth,
        topic=topic,
        kind=kind,
        research=research,
    )
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

    rows = tavily_search(q, max_results=DEFAULT_MAX_RESULTS, kind=kind)
    for row in rows:
        text = str(row.get("content") or row.get("snippet") or "").strip()
        if len(text) >= 30:
            return fit_voice_spoken(text, max_chars=max_chars)
    if rows:
        title = str(rows[0].get("title") or "").strip()
        return fit_voice_spoken(title, max_chars=max_chars) if title else ""
    return ""
