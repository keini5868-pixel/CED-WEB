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

# Bare "PM" acronym noise (Wikipedia disambiguation, ante meridiem, etc.)
_PM_ACRONYM_NOISE = re.compile(
    r"(?:"
    r"disambiguation|may\s+refer\s+to|stands?\s+for|"
    r"ante\s*meridiem|post\s*meridiem|"
    r"\bpm\b\s*(?:and|/|\|)\s*\bam\b|"
    r"\bam\b\s*(?:and|/|\|)\s*\bpm\b|"
    r"prime\s+minister|project\s+manager|particulate\s+matter|"
    r"wikipedia\.org/wiki/pm\b|wikipedia\.org/wiki/pm_"
    r")",
    re.I,
)

_ENTITY_OK = re.compile(
    r"(?:"
    r"pm[\s\-]?international|fitline|fit\s*line|"
    r"pm\-international\.com|fitline\.com"
    r")",
    re.I,
)

# First-person / distributor marketing presented as "facts"
_PROMOTIONAL = re.compile(
    r"(?:"
    r"\b(?:we have|we've|we're|i have|i've|i made|i am|i'm|"
    r"my name is|my team|join my|contact me|dm me|message me|"
    r"changed my life|truly a historic|historic moment for|"
    r"highest compensation|best compensation|"
    r"pay(?:s|ing)?\s+out\s+there|unbelievable\s+(?:income|payout)|"
    r"life[- ]changing\s+(?:income|opportunity)|"
    r"i(?:'m| am)\s+a\s+(?:distributor|partner|leader)|"
    r"hello,?\s+my\s+name)\b"
    r"|!\s*(?:truly|amazing|incredible)"
    r")",
    re.I,
)

_BARE_PM_TOKEN = re.compile(r"(?<![A-Za-z])PM(?![A-Za-z\-])")


def _normalize_anchors(anchors: list[str]) -> list[str]:
    """Never allow bare 'PM' — expand to full company/product phrases."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in anchors:
        a = re.sub(r"\s+", " ", (raw or "").strip())
        if not a:
            continue
        # Replace isolated PM with full name when International/FitLine missing
        if _BARE_PM_TOKEN.search(a) and not re.search(
            r"pm[\s\-]?international|fitline", a, re.I
        ):
            a = _BARE_PM_TOKEN.sub("PM International", a)
        if a.lower() in ("pm", "p.m.", "p.m"):
            a = "PM International"
        key = a.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(a[:140])
    # Always ensure both brand phrases when FitLine/PMI catalog
    joined = " ".join(out).lower()
    if "fitline" in joined or "pm international" in joined or "pm-international" in joined:
        for must in ("PM International", "FitLine"):
            if must.lower() not in joined:
                out.append(must)
                joined = " ".join(out).lower()
    return out[:6]


def build_opportunity_queries(anchors: list[str]) -> list[dict[str, str]]:
    norms = _normalize_anchors(anchors)
    if not norms:
        return []
    # Quoted full phrases — never bare PM
    quoted = " ".join(f'"{a}"' for a in norms[:2])
    primary = norms[0]
    secondary = norms[1] if len(norms) > 1 else "FitLine"
    return [
        {
            "purpose": "official",
            "query": (
                f'{quoted} "PM International" FitLine official company '
                "business opportunity 2025 2026 -disambiguation"
            ).strip()[:380],
        },
        {
            "purpose": "requirements",
            "query": (
                f'"PM International" "{secondary}" starter package '
                "manager requirements how to start -disambiguation"
            ).strip()[:380],
        },
        {
            "purpose": "compensation",
            "query": (
                f'"PM International" FitLine compensation plan '
                "official residual income site:pm-international.com OR "
                "site:fitline.com -crypto -token -disambiguation"
            ).strip()[:380],
        },
        {
            "purpose": "official",
            "query": (
                f'"{primary}" FitLine nutrition wellness company overview'
            ).strip()[:380],
        },
    ]


def is_promotional_or_testimonial(title: str, snippet: str) -> bool:
    blob = f"{title} {snippet}"
    return bool(_PROMOTIONAL.search(blob))


def _row_ok(title: str, snippet: str, url: str) -> bool:
    blob = f"{title} {snippet} {url}"
    if _CRYPTO_FINANCE.search(blob):
        logger.info(
            "[OPPS-PILOT] drop off-category title=%s", (title or "")[:80]
        )
        return False
    # Require real entity — blocks bare-PM Wikipedia / clock definitions
    if not _ENTITY_OK.search(blob):
        logger.info(
            "[OPPS-PILOT] drop missing entity title=%s", (title or "")[:80]
        )
        return False
    if _PM_ACRONYM_NOISE.search(blob) and not re.search(
        r"pm[\s\-]?international|fitline", blob, re.I
    ):
        logger.info(
            "[OPPS-PILOT] drop PM-acronym noise title=%s", (title or "")[:80]
        )
        return False
    if is_promotional_or_testimonial(title, snippet):
        logger.info(
            "[OPPS-PILOT] drop promotional/testimonial title=%s",
            (title or "")[:80],
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
        "dropped_promotional": 0,
        "dropped_noise": 0,
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
            "dropped_promotional": 0,
            "dropped_noise": 0,
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
            if is_promotional_or_testimonial(title, content):
                info["dropped_promotional"] += 1
                continue
            if not _row_ok(title, content, url):
                info["dropped_noise"] += 1
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

    with ThreadPoolExecutor(max_workers=min(4, len(queries))) as pool:
        futures = {pool.submit(_one, q): q for q in queries}
        for fut in as_completed(futures):
            try:
                batch, info = fut.result()
                sources.extend(batch)
                meta["result_rows"] += int(info.get("n_results") or 0)
                meta["dropped_promotional"] += int(
                    info.get("dropped_promotional") or 0
                )
                meta["dropped_noise"] += int(info.get("dropped_noise") or 0)
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
    """Hechos de búsqueda agrupados por purpose — solo citables (no testimoniales)."""
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
        title = str(src.get("title") or "")
        if len(snippet) < 40:
            continue
        if is_promotional_or_testimonial(title, snippet):
            continue
        buckets[purpose].append(
            {
                "text": snippet[:260],
                "source_title": title,
                "source_url": str(src.get("url") or ""),
                "attribution": "search",
            }
        )
    for key in buckets:
        buckets[key] = buckets[key][:3]
    return buckets
