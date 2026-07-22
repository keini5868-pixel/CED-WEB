"""Búsquedas dirigidas de tendencias — hechos atribuibles a la sesión."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from app.services.tavily_search import tavily_raw_search

logger = logging.getLogger(__name__)

MAX_RESULTS = 5
SNIPPET_MAX = 420
TIMEOUT_SEC = 14.0


def build_trends_queries(
    anchor: str,
    *,
    region: str | None = None,
) -> list[dict[str, str]]:
    a = (anchor or "").strip()[:140]
    if not a:
        return []
    loc = (region or "").strip()[:80]
    loc_s = f" {loc}" if loc else ""
    return [
        {
            "purpose": "trending_now",
            "query": f"{a} trends 2025 2026 what's trending{loc_s}".strip(),
        },
        {
            "purpose": "consumer_needs",
            "query": (
                f"{a} consumer needs pain points emerging demand{loc_s}"
            ).strip(),
        },
        {
            "purpose": "outlook_6m",
            "query": (
                f"{a} market outlook forecast next 6 months 2026{loc_s}"
            ).strip(),
        },
        {
            "purpose": "opportunities",
            "query": (
                f"{a} emerging opportunities niches growth{loc_s}"
            ).strip(),
        },
    ]


def _row_to_source(row: dict[str, Any], *, query: str, purpose: str) -> dict[str, Any] | None:
    title = str(row.get("title") or "").strip()
    url = str(row.get("url") or "").strip()
    content = str(row.get("content") or row.get("snippet") or "").strip()
    if not content and not title:
        return None
    return {
        "purpose": purpose,
        "query": query,
        "title": title or "(sin título)",
        "url": url,
        "snippet": content[:SNIPPET_MAX],
    }


def run_trends_searches(queries: list[dict[str, str]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    meta: dict[str, Any] = {
        "queries_run": len(queries),
        "result_rows": 0,
        "answers": 0,
        "errors": [],
        "rate_limited": False,
        "missing_key": False,
        "sources": 0,
    }
    if not queries:
        return sources, meta

    def _one(item: dict[str, str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        q = item["query"]
        purpose = item["purpose"]
        data = tavily_raw_search(
            q,
            max_results=MAX_RESULTS,
            kind="general",
            timeout_sec=TIMEOUT_SEC,
        )
        info = {
            "query": q,
            "purpose": purpose,
            "error": data.get("error"),
            "rate_limited": bool(data.get("rate_limited")),
            "n_results": len(data.get("results") or []),
            "has_answer": bool(
                isinstance(data.get("answer"), str)
                and len(str(data.get("answer")).strip()) >= 40
            ),
        }
        out: list[dict[str, Any]] = []
        answer = data.get("answer")
        if isinstance(answer, str) and len(answer.strip()) >= 40:
            out.append(
                {
                    "purpose": purpose,
                    "query": q,
                    "title": "Resumen Tavily",
                    "url": "",
                    "snippet": answer.strip()[:SNIPPET_MAX],
                }
            )
        for row in data.get("results") or []:
            if isinstance(row, dict):
                src = _row_to_source(row, query=q, purpose=purpose)
                if src:
                    out.append(src)
        return out, info

    with ThreadPoolExecutor(max_workers=min(4, len(queries))) as pool:
        futures = {pool.submit(_one, q): q for q in queries}
        for fut in as_completed(futures):
            try:
                batch, info = fut.result()
                sources.extend(batch)
                meta["result_rows"] += int(info.get("n_results") or 0)
                if info.get("has_answer"):
                    meta["answers"] += 1
                if info.get("rate_limited"):
                    meta["rate_limited"] = True
                err = info.get("error")
                if err:
                    if err == "missing_tavily_key":
                        meta["missing_key"] = True
                    meta["errors"].append(
                        {
                            "purpose": info.get("purpose"),
                            "query": info.get("query"),
                            "error": err,
                        }
                    )
            except Exception:  # noqa: BLE001
                logger.exception("[TRENDS-PILOT] search failed")
                meta["errors"].append({"error": "exception"})

    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for src in sources:
        key = f"{src.get('url')}|{(src.get('snippet') or '')[:80]}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(src)
    meta["sources"] = len(unique)
    if not unique:
        logger.warning(
            "[TRENDS-PILOT] ZERO sources errors=%s rate_limited=%s",
            meta.get("errors"),
            meta.get("rate_limited"),
        )
    return unique, meta


def extract_trend_facts(sources: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Agrupa snippets por purpose — solo hechos de la sesión."""
    buckets: dict[str, list[dict[str, Any]]] = {
        "trending_now": [],
        "consumer_needs": [],
        "outlook_6m": [],
        "opportunities": [],
    }
    for src in sources:
        purpose = str(src.get("purpose") or "")
        if purpose not in buckets:
            continue
        snippet = str(src.get("snippet") or "").strip()
        if len(snippet) < 40:
            continue
        buckets[purpose].append(
            {
                "text": snippet[:280],
                "source_title": src.get("title") or "",
                "source_url": src.get("url") or "",
                "query": src.get("query") or "",
                "attribution": "search",
            }
        )
    # Cap per bucket
    for key in buckets:
        buckets[key] = buckets[key][:5]
    return buckets
