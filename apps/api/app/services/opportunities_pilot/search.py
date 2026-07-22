"""Búsqueda anclada para actualizar hechos de una oportunidad."""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from app.services.tavily_search import tavily_raw_search

logger = logging.getLogger(__name__)

MAX_RESULTS = 4
SNIPPET_MAX = 400
TIMEOUT_SEC = 12.0

_CRYPTO_FINANCE = re.compile(
    r"(?:"
    r"\b(?:cryptocurrenc\w*|crypto(?:currency)?|memecoin|tokenomics|"
    r"blockchain|binance|coinbase|price\s*prediction)\b"
    r"|\$0\.0+\d+"
    r")",
    re.I,
)


def build_opportunity_queries(anchors: list[str]) -> list[dict[str, str]]:
    primary = (anchors[0] if anchors else "").strip()[:120]
    if not primary:
        return []
    return [
        {
            "purpose": "official",
            "query": f"{primary} official company business opportunity 2025 2026",
        },
        {
            "purpose": "requirements",
            "query": f"{primary} starter package requirements how to join",
        },
        {
            "purpose": "compensation",
            "query": (
                f"{primary} compensation plan income residual "
                "official -crypto -token"
            ),
        },
    ]


def _row_ok(title: str, snippet: str, url: str) -> bool:
    blob = f"{title} {snippet} {url}"
    if _CRYPTO_FINANCE.search(blob):
        logger.info(
            "[OPPS-PILOT] drop off-category title=%s", (title or "")[:80]
        )
        return False
    return True


def run_opportunity_searches(
    queries: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    meta: dict[str, Any] = {
        "queries_run": len(queries),
        "result_rows": 0,
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
        }
        out: list[dict[str, Any]] = []
        for row in data.get("results") or []:
            if not isinstance(row, dict):
                continue
            title = str(row.get("title") or "").strip()
            url = str(row.get("url") or "").strip()
            content = str(row.get("content") or row.get("snippet") or "").strip()
            if len(content) < 40 and not title:
                continue
            if not _row_ok(title, content, url):
                continue
            out.append(
                {
                    "purpose": purpose,
                    "query": q,
                    "title": title or "(sin título)",
                    "url": url,
                    "snippet": content[:SNIPPET_MAX],
                    "attribution": "search",
                }
            )
        return out, info

    with ThreadPoolExecutor(max_workers=min(3, len(queries))) as pool:
        futures = {pool.submit(_one, q): q for q in queries}
        for fut in as_completed(futures):
            try:
                batch, info = fut.result()
                sources.extend(batch)
                meta["result_rows"] += int(info.get("n_results") or 0)
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
                logger.exception("[OPPS-PILOT] search failed")
                meta["errors"].append({"error": "exception"})

    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for src in sources:
        key = f"{src.get('url')}|{(src.get('snippet') or '')[:60]}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(src)
    meta["sources"] = len(unique)
    return unique, meta


def extract_search_updates(
    sources: list[dict[str, Any]],
) -> dict[str, list[dict[str, str]]]:
    """Hechos de búsqueda agrupados por purpose — solo citables."""
    buckets: dict[str, list[dict[str, str]]] = {
        "official": [],
        "requirements": [],
        "compensation": [],
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
                "text": snippet[:260],
                "source_title": str(src.get("title") or ""),
                "source_url": str(src.get("url") or ""),
                "attribution": "search",
            }
        )
    for key in buckets:
        buckets[key] = buckets[key][:3]
    return buckets
