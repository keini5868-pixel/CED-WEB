"""Búsquedas dirigidas de tendencias — hechos atribuibles a la sesión."""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from app.services.tavily_search import tavily_raw_search

logger = logging.getLogger(__name__)

MAX_RESULTS = 5
SNIPPET_MAX = 420
TIMEOUT_SEC = 14.0

# Off-category: finance/crypto noise when the anchor is a physical product.
_CRYPTO_FINANCE = re.compile(
    r"(?:"
    r"\b(?:cryptocurrenc\w*|crypto(?:currency)?|memecoin|altcoin|stablecoin|"
    r"blockchain|defi\b|web3|tokenomics|airdrop|hodl|satoshi|"
    r"binance|coinbase|kraken|dex\b|cex\b|liquidity\s*pool|"
    r"market\s*cap|fully\s*diluted|fdv\b|trading\s*pair|"
    r"price\s*prediction|predicc(?:i[oó]n)?\s*(?:de\s*)?(?:precio|price)|"
    r"token\s+price|precio\s+del\s+token|crypto\s*token|"
    r"nft\s*(?:floor|mint)|stock\s*ticker|equity\s*share)\b"
    r"|\$0\.0+\d+"
    r"|(?:alcanzar|reach(?:es|ing)?|target(?:s|ing)?)\s+\$?\d*\.?\d+\s*"
    r"(?:por|by|in)\s*20\d{2}"
    r")",
    re.I,
)

_PHYSICAL_SIGNAL = re.compile(
    r"\b("
    r"figuras?|figurines?|action\s*figures?|coleccion(?:able)?s?|collectibles?|"
    r"juguetes?|toys?|merchandis\w*|estatuas?|statues?|plush|funko|nendoroid|"
    r"retail|walmart|amazon|suplementos?|alimentos?|cafeter\w*|ropa|calzado|"
    r"producto\s*f[ií]sico|shipping|env[ií]o|sku\b|inventario|inventory"
    r")\b",
    re.I,
)


def build_trends_queries(
    anchor: str,
    *,
    region: str | None = None,
    category: str | None = None,
    product_kind: str | None = None,
) -> list[dict[str, str]]:
    a = (anchor or "").strip()[:140]
    if not a:
        return []
    loc = (region or "").strip()[:80]
    loc_s = f" {loc}" if loc else ""
    cat = (category or "").strip()[:80]
    kind = (product_kind or "").strip()

    # Disambiguate named entities that collide with unrelated markets (e.g. Goku
    # figures vs GOKU crypto token).
    focus = a
    if cat and cat.lower() not in a.lower():
        focus = f"{a} {cat}".strip()[:180]
    elif kind == "physical_good":
        focus = f"{a} physical product retail".strip()[:180]

    crypto_guard = ""
    if kind == "physical_good" or (
        cat and re.search(r"figura|collect|juguete|merch|retail|suplement", cat, re.I)
    ):
        crypto_guard = " -crypto -token -cryptocurrency -blockchain"

    return [
        {
            "purpose": "trending_now",
            "query": f"{focus} trends 2025 2026 what's trending{loc_s}{crypto_guard}".strip(),
        },
        {
            "purpose": "consumer_needs",
            "query": (
                f"{focus} consumer needs pain points emerging demand{loc_s}{crypto_guard}"
            ).strip(),
        },
        {
            "purpose": "outlook_6m",
            "query": (
                f"{focus} industry demand outlook collectors market next 6 months 2026"
                f"{loc_s}{crypto_guard}"
            ).strip()
            if kind == "physical_good"
            or (cat and re.search(r"figura|collect|juguete|merch", cat, re.I))
            else (
                f"{focus} market outlook demand forecast next 6 months 2026"
                f"{loc_s}{crypto_guard}"
            ).strip(),
        },
        {
            "purpose": "opportunities",
            "query": (
                f"{focus} emerging opportunities niches growth{loc_s}{crypto_guard}"
            ).strip(),
        },
    ]


def source_matches_category(
    *,
    title: str,
    snippet: str,
    url: str = "",
    profile: dict[str, Any] | None = None,
) -> bool:
    """Reject results from a clearly different market than the user's anchor.

    Same idea as VIABLE same-category/use: when the anchor is a physical good,
    drop crypto/finance price-prediction noise even if the name overlaps.
    """
    profile = profile or {}
    kind = str(profile.get("product_kind") or "")
    category = str(profile.get("category") or "")
    anchor = str(profile.get("anchor") or "")
    blob = f"{title} {snippet} {url}"

    physical_anchor = kind == "physical_good" or bool(
        re.search(
            r"figura|collect|juguete|merch|suplement|cafeter|ropa|alimento",
            f"{category} {anchor}",
            re.I,
        )
    )
    if not physical_anchor:
        return True

    if not _CRYPTO_FINANCE.search(blob):
        return True

    # Crypto/finance hit: only keep if the same snippet also clearly talks about
    # the physical product category (rare). Prefer discard.
    if _PHYSICAL_SIGNAL.search(blob) and not re.search(
        r"\b(?:token|crypto|blockchain|\$0\.0)\b", blob, re.I
    ):
        return True

    logger.info(
        "[TRENDS-PILOT] drop off-category (crypto/finance) title=%s",
        (title or "")[:80],
    )
    return False


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
        "dropped_off_category": 0,
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


def extract_trend_facts(
    sources: list[dict[str, Any]],
    *,
    profile: dict[str, Any] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Agrupa snippets por purpose — solo hechos de la sesión y misma categoría."""
    buckets: dict[str, list[dict[str, Any]]] = {
        "trending_now": [],
        "consumer_needs": [],
        "outlook_6m": [],
        "opportunities": [],
    }
    dropped = 0
    for src in sources:
        purpose = str(src.get("purpose") or "")
        if purpose not in buckets:
            continue
        snippet = str(src.get("snippet") or "").strip()
        if len(snippet) < 40:
            continue
        title = str(src.get("title") or "")
        url = str(src.get("url") or "")
        if not source_matches_category(
            title=title, snippet=snippet, url=url, profile=profile
        ):
            dropped += 1
            continue
        buckets[purpose].append(
            {
                "text": snippet[:280],
                "source_title": title,
                "source_url": url,
                "query": src.get("query") or "",
                "attribution": "search",
            }
        )
    if dropped:
        logger.info("[TRENDS-PILOT] off-category drops=%s", dropped)
    # Cap per bucket
    for key in buckets:
        buckets[key] = buckets[key][:5]
    return buckets
