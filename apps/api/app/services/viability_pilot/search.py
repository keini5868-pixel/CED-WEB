"""Búsquedas web dirigidas + extracción de hechos atribuibles (anti-alucinación)."""

from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from app.services.tavily_search import tavily_raw_search

logger = logging.getLogger(__name__)

MAX_QUERIES = 4
MAX_RESULTS_PER_QUERY = 5
SNIPPET_MAX = 420
VIABILITY_TAVILY_TIMEOUT_SEC = 14.0

_EN_REGION = re.compile(
    r"\b("
    r"estados\s+unidos|united\s+states|\busa\b|u\.s\.a?\.?|"
    r"\buk\b|united\s+kingdom|canada|australia|england|ee\.?\s?uu\.?"
    r")\b",
    re.I,
)
_RETAIL_PRODUCT = re.compile(
    r"\b("
    r"perfume|fragancia|fragrance|eau\s+de|edp|edt|"
    r"chanel|dior|gucci|nike|adidas|iphone|samsung|"
    r"crema|shampoo|serum|maquillaje|zapat|sneaker|sku|"
    r"amazon|sephora|walmart|retail"
    r")\b",
    re.I,
)

# Currency prices — avoid matching "s/" inside https://
_PRICEISH = re.compile(
    r"(?:"
    r"(?:USD|US\$|EUR|MXN|COP|ARS|CLP|PEN)\s*[\d]{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?"
    r"|(?<![A-Za-z0-9])\$(?!\s*\{)\s?[\d]{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?"
    r"|(?<![A-Za-z0-9])€\s?[\d]{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?"
    r"|\bS/\s*[\d]{1,5}(?:[.,]\d{2})?"
    r"|(?:desde|aprox\.?|alrededor de|starting from|from)\s+\$?\s?[\d]{1,6}"
    r"|[\d]{1,4}\s*(?:USD|dólares|euros)(?:/(?:mes|hora|sesión|oz|ml))?"
    r")",
    re.IGNORECASE,
)

_GENERIC_NAME_BLOCK = re.compile(
    r"^(?:"
    r"in|the|a|an|el|la|los|las|de|del|en|para|con|por|un|una|"
    r"best|top|mejores|alternativas|competidores|competitors|"
    r"mercado|market|precio|precios|price|pricing|tendencias|trends|"
    r"santo domingo|mexico|méxico|cdmx|pymes|pyme|usa|latam|"
    r"wikipedia|home|inicio|resumen tavily|escuela|limpieza|cafeteria|cafetería"
    r")$",
    re.IGNORECASE,
)


def _prefer_english_queries(offering: str, region: str | None) -> bool:
    """Retail / US-centric offerings get English market queries (Amazon, Sephora, etc.)."""
    return bool(_EN_REGION.search(region or "") or _RETAIL_PRODUCT.search(offering or ""))


def build_search_queries(
    offering: str,
    *,
    region: str | None = None,
    category_hint: str | None = None,
) -> list[dict[str, str]]:
    """Consultas específicas — retail/EN cuando aplica; no una sola búsqueda genérica."""
    topic = (offering or "").strip()[:180]
    if not topic:
        return []
    loc = (region or "").strip()[:80]
    cat = (category_hint or "").strip()[:80]
    base = f"{cat} {topic}".strip() if cat and cat.lower() not in topic.lower() else topic
    loc_suffix = f" {loc}" if loc else ""
    english = _prefer_english_queries(base, loc)

    if english:
        return [
            {
                "purpose": "competitors",
                "query": f"{base} competitors alternatives similar products{loc_suffix}",
            },
            {
                "purpose": "pricing",
                "query": f"{base} price USD buy Sephora Amazon{loc_suffix}",
            },
            {
                "purpose": "trends",
                "query": f"{base} market trends 2025 2026 demand popularity{loc_suffix}",
            },
            {
                "purpose": "comparables",
                "query": f"best alternatives to {base} vs comparison{loc_suffix}",
            },
        ][:MAX_QUERIES]

    return [
        {
            "purpose": "competitors",
            "query": f"{base} competidores alternativas{loc_suffix}",
        },
        {
            "purpose": "pricing",
            "query": f"{base} precio típico cuánto cuesta tarifas{loc_suffix}",
        },
        {
            "purpose": "trends",
            "query": f"{base} tendencias mercado 2025 2026 demanda{loc_suffix}",
        },
        {
            "purpose": "comparables",
            "query": (
                f"mejores {base} vs competencia market share{loc_suffix}"
                if len(base) < 100
                else f"{base} landscape competencia{loc_suffix}"
            ),
        },
    ][:MAX_QUERIES]


def _fallback_english_queries(offering: str, region: str | None) -> list[dict[str, str]]:
    topic = (offering or "").strip()[:180]
    loc = (region or "").strip()[:80]
    loc_suffix = f" {loc}" if loc else ""
    return [
        {
            "purpose": "competitors",
            "query": f"{topic} competitors alternatives{loc_suffix}",
        },
        {
            "purpose": "pricing",
            "query": f"{topic} price cost buy online{loc_suffix}",
        },
    ]


def _row_to_source(row: dict[str, Any], *, query: str, purpose: str) -> dict[str, Any] | None:
    title = str(row.get("title") or "").strip()
    url = str(row.get("url") or "").strip()
    content = str(row.get("content") or row.get("snippet") or "").strip()
    if not content and not title:
        return None
    snippet = content[:SNIPPET_MAX]
    return {
        "purpose": purpose,
        "query": query,
        "title": title or "(sin título)",
        "url": url,
        "snippet": snippet,
    }


def _execute_query_batch(queries: list[dict[str, str]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Ejecuta batch; propaga errores/rate-limits (no tragárselos en silencio)."""
    sources: list[dict[str, Any]] = []
    meta: dict[str, Any] = {
        "queries_run": len(queries),
        "result_rows": 0,
        "answers": 0,
        "errors": [],
        "rate_limited": False,
        "missing_key": False,
    }
    if not queries:
        return sources, meta

    def _one(item: dict[str, str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        q = item["query"]
        purpose = item["purpose"]
        data = tavily_raw_search(
            q,
            max_results=MAX_RESULTS_PER_QUERY,
            kind="general",
            timeout_sec=VIABILITY_TAVILY_TIMEOUT_SEC,
        )
        info: dict[str, Any] = {
            "query": q,
            "purpose": purpose,
            "error": data.get("error"),
            "rate_limited": bool(data.get("rate_limited")),
            "n_results": len(data.get("results") or []),
            "has_answer": bool(
                isinstance(data.get("answer"), str) and len(str(data.get("answer")).strip()) >= 40
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
            if not isinstance(row, dict):
                continue
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
                        {"purpose": info.get("purpose"), "query": info.get("query"), "error": err}
                    )
            except Exception as exc:  # noqa: BLE001
                logger.exception("[VIABILITY-PILOT] search failed")
                meta["errors"].append({"error": f"exception:{type(exc).__name__}"})

    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for src in sources:
        key = f"{src.get('url')}|{(src.get('snippet') or '')[:80]}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(src)
    meta["sources"] = len(unique)
    return unique, meta


def run_targeted_searches(
    queries: list[dict[str, str]],
    *,
    offering: str = "",
    region: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Ejecuta búsquedas; si vienen muy pocas, reintenta con queries EN retail."""
    sources, meta = _execute_query_batch(queries)
    meta["fallback_used"] = False

    thin = len(sources) < 3 or (
        meta["result_rows"] == 0 and meta["answers"] == 0
    )
    if thin and offering.strip():
        fb = _fallback_english_queries(offering, region)
        # Evitar duplicar queries idénticas
        existing_q = {q["query"].lower() for q in queries}
        fb = [q for q in fb if q["query"].lower() not in existing_q]
        if fb:
            logger.warning(
                "[VIABILITY-PILOT] thin search sources=%s — english fallback",
                len(sources),
            )
            extra, meta2 = _execute_query_batch(fb)
            meta["fallback_used"] = True
            meta["fallback_meta"] = meta2
            # merge
            seen = {f"{s.get('url')}|{(s.get('snippet') or '')[:80]}" for s in sources}
            for src in extra:
                key = f"{src.get('url')}|{(src.get('snippet') or '')[:80]}"
                if key in seen:
                    continue
                seen.add(key)
                sources.append(src)
            meta["sources"] = len(sources)
            meta["result_rows"] += int(meta2.get("result_rows") or 0)
            meta["answers"] += int(meta2.get("answers") or 0)
            if meta2.get("rate_limited"):
                meta["rate_limited"] = True
            meta["errors"].extend(meta2.get("errors") or [])

    if not sources:
        logger.warning(
            "[VIABILITY-PILOT] ZERO sources after search errors=%s rate_limited=%s",
            meta.get("errors"),
            meta.get("rate_limited"),
        )
    return sources, meta


def _name_appears_in_source(name: str, src: dict[str, Any]) -> bool:
    blob = f"{src.get('title') or ''} {src.get('snippet') or ''}"
    return name.lower() in blob.lower()


def _backfill_source_url(name: str, preferred: dict[str, Any], sources: list[dict[str, Any]]) -> dict[str, Any]:
    """Si el hit vino del resumen Tavily (sin URL), busca un result con URL que cite el nombre."""
    if (preferred.get("url") or "").strip():
        return preferred
    for src in sources:
        url = (src.get("url") or "").strip()
        if not url:
            continue
        if _name_appears_in_source(name, src):
            return {
                "title": src.get("title") or preferred.get("title"),
                "url": url,
                "query": src.get("query") or preferred.get("query"),
                "snippet": (src.get("snippet") or preferred.get("snippet") or "")[:200],
            }
    return preferred


def _is_plausible_competitor_name(name: str) -> bool:
    n = (name or "").strip()
    if len(n) < 3 or len(n) > 60:
        return False
    if _GENERIC_NAME_BLOCK.match(n):
        return False
    words = n.split()
    if len(words) == 1 and n.islower():
        return False
    if re.fullmatch(r"[\d\W]+", n):
        return False
    low = n.lower()
    # Reject SEO listicle titles mistaken for brands
    if re.match(r"^(\d+|best|top|el mejor|mejores)\b", low):
        return False
    if any(tok in low for tok in (" dupe", "dupes", " clone", "clones", " alternative")):
        return False
    if low.endswith((" dupes", " clones", " alternatives")):
        return False
    return True


def _extract_competitors_llm(
    offering: str,
    sources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Nombres de competidores solo si aparecen verbatim en un source de la sesión."""
    from app.config import get_settings

    api_key = get_settings().google_api_key.strip()
    if not api_key or not sources:
        return []

    indexed = []
    for i, src in enumerate(sources[:16]):
        indexed.append(
            {
                "i": i,
                "purpose": src.get("purpose"),
                "title": (src.get("title") or "")[:120],
                "url": (src.get("url") or "")[:200],
                "snippet": (src.get("snippet") or "")[:320],
            }
        )

    prompt = (
        "Extrae hasta 3 competidores, alternativas o productos comparables REALES. "
        "Sirve tanto para negocios locales como para productos retail (ej. perfumes, "
        "electrónica). SOLO nombres que aparezcan literalmente en title/snippet. "
        "Si el producto analizado es una marca conocida, lista alternativas/competidores "
        "mencionados (no repitas solo el mismo producto). "
        "Si no hay nombres claros, lista vacía. NO inventes. "
        'JSON: {"competitors":[{"name":"...","note":"una linea","source_index":0}]}\n'
        f"Oferta: {offering[:400]}\n"
        f"Fuentes:\n{json.dumps(indexed, ensure_ascii=False)[:9000]}"
    )
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=800,
                response_mime_type="application/json",
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        text = (getattr(response, "text", None) or "").strip()
        if not text:
            return []
        data = json.loads(text)
        rows = data.get("competitors") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            return []
    except Exception:  # noqa: BLE001
        logger.warning("[VIABILITY-PILOT] competitor LLM extract failed", exc_info=True)
        return []

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        note = str(row.get("note") or "").strip()[:180]
        try:
            idx = int(row.get("source_index"))
        except (TypeError, ValueError):
            continue
        if idx < 0 or idx >= len(sources):
            continue
        src = sources[idx]
        if not _is_plausible_competitor_name(name):
            continue
        if not _name_appears_in_source(name, src):
            # Nombre puede estar en otro source del batch
            alt = next((s for s in sources if _name_appears_in_source(name, s)), None)
            if not alt:
                continue
            src = alt
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        cite = _backfill_source_url(
            name,
            {
                "title": src.get("title"),
                "url": src.get("url"),
                "query": src.get("query"),
                "snippet": (src.get("snippet") or "")[:200],
            },
            sources,
        )
        out.append(
            {
                "name": name,
                "note": note or (src.get("snippet") or "")[:160],
                "source": cite,
            }
        )
        if len(out) >= 3:
            break
    return out


def _extract_competitors_heuristic(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fallback: marcas citadas en snippets + títulos con URL."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    # Prefer explicit "include X, Y, and Z" lists from Tavily answers
    listish = re.compile(
        r"(?:include|includes|alternatives?(?:\s+to[^:]+)?:|dupes?(?:\s+include)?)\s+"
        r"([A-Z][^.]{10,180})",
        re.I,
    )
    brandish = re.compile(
        r"\b([A-Z][A-Za-z0-9'&.-]{1,20}(?:\s+[A-Z][A-Za-z0-9'&.-]{1,20}){0,3})\b"
    )

    for src in sources:
        if (src.get("purpose") or "") not in ("competitors", "comparables"):
            continue
        snippet = str(src.get("snippet") or "")
        for block in listish.findall(snippet):
            # split on commas / and /
            parts = re.split(r",|/|\band\b", block)
            for part in parts:
                name = part.strip(" .;:")
                name = re.sub(r"\s+\(.*$", "", name).strip()
                if not _is_plausible_competitor_name(name):
                    continue
                if not _name_appears_in_source(name, src) and name.lower() not in snippet.lower():
                    continue
                key = name.lower()
                if key in seen:
                    continue
                seen.add(key)
                cite = _backfill_source_url(
                    name,
                    {
                        "title": src.get("title"),
                        "url": src.get("url"),
                        "query": src.get("query"),
                        "snippet": snippet[:200],
                    },
                    sources,
                )
                out.append({"name": name, "note": snippet[:160], "source": cite})
                if len(out) >= 3:
                    return out

        for m in brandish.finditer(snippet[:350]):
            name = m.group(1).strip()
            if not _is_plausible_competitor_name(name):
                continue
            if len(name.split()) < 2:
                continue
            key = name.lower()
            if key in seen:
                continue
            # skip the offering itself if clearly the same product line
            seen.add(key)
            cite = _backfill_source_url(
                name,
                {
                    "title": src.get("title"),
                    "url": src.get("url"),
                    "query": src.get("query"),
                    "snippet": snippet[:200],
                },
                sources,
            )
            out.append({"name": name, "note": snippet[:160], "source": cite})
            if len(out) >= 3:
                return out

    return out


def extract_attributed_facts(
    sources: list[dict[str, Any]],
    *,
    offering: str = "",
) -> dict[str, Any]:
    """Extrae hechos atribuibles — competidores validados contra snippets de la sesión."""
    prices: list[dict[str, Any]] = []
    trend_notes: list[dict[str, Any]] = []

    for src in sources:
        purpose = src.get("purpose") or ""
        snippet = str(src.get("snippet") or "")
        title = str(src.get("title") or "")
        cite = {
            "title": title,
            "url": src.get("url") or "",
            "query": src.get("query"),
            "snippet": snippet[:200],
        }

        # Precios en cualquier purpose si el regex matchea (retail suele traer $ en varias queries)
        if purpose == "pricing" or _PRICEISH.search(snippet):
            for pm in _PRICEISH.finditer(snippet):
                text = pm.group(0).strip()
                # Drop bogus fragments
                if re.fullmatch(r"s/\s*\d", text, re.I):
                    continue
                if len(text) < 2:
                    continue
                prices.append(
                    {
                        "text": text,
                        "context": snippet[:200],
                        "source": cite,
                    }
                )

        if purpose == "trends" and len(snippet) >= 40:
            trend_notes.append({"text": snippet[:280], "source": cite})

    competitors = _extract_competitors_llm(offering, sources)
    if len(competitors) < 2:
        for c in _extract_competitors_heuristic(sources):
            if c["name"].lower() in {x["name"].lower() for x in competitors}:
                continue
            competitors.append(c)
            if len(competitors) >= 3:
                break

    uniq_prices: list[dict[str, Any]] = []
    seen_p: set[str] = set()
    for p in prices:
        key = p["text"].lower()
        if key in seen_p:
            continue
        seen_p.add(key)
        uniq_prices.append(p)
        if len(uniq_prices) >= 8:
            break

    return {
        "competitors": competitors[:3],
        "prices": uniq_prices,
        "trends": trend_notes[:6],
        "source_count": len(sources),
    }
