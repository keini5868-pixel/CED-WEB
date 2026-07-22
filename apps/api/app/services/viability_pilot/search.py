"""Búsquedas web dirigidas + extracción de hechos atribuibles (anti-alucinación)."""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from app.services.tavily_search import tavily_raw_search

logger = logging.getLogger(__name__)

MAX_QUERIES = 4
MAX_RESULTS_PER_QUERY = 5
SNIPPET_MAX = 420


def build_search_queries(
    offering: str,
    *,
    region: str | None = None,
    category_hint: str | None = None,
) -> list[dict[str, str]]:
    """Consultas específicas — no una sola búsqueda genérica."""
    topic = (offering or "").strip()[:180]
    if not topic:
        return []
    loc = (region or "").strip()[:80]
    cat = (category_hint or "").strip()[:80]
    base = f"{cat} {topic}".strip() if cat and cat.lower() not in topic.lower() else topic
    loc_suffix = f" {loc}" if loc else ""

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


def run_targeted_searches(queries: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Ejecuta búsquedas en paralelo; cada hecho queda ligado a URL/query."""
    sources: list[dict[str, Any]] = []
    if not queries:
        return sources

    def _one(item: dict[str, str]) -> list[dict[str, Any]]:
        q = item["query"]
        purpose = item["purpose"]
        data = tavily_raw_search(q, max_results=MAX_RESULTS_PER_QUERY, kind="general")
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
        return out

    with ThreadPoolExecutor(max_workers=min(4, len(queries))) as pool:
        futures = {pool.submit(_one, q): q for q in queries}
        for fut in as_completed(futures):
            try:
                sources.extend(fut.result())
            except Exception:  # noqa: BLE001
                logger.exception("[VIABILITY-PILOT] search failed")

    # Dedup por URL+snippet corto
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for src in sources:
        key = f"{src.get('url')}|{(src.get('snippet') or '')[:80]}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(src)
    return unique


_PRICEISH = re.compile(
    r"(?:USD|US\$|\$|€|MXN|COP|ARS|CLP|PEN|S/\.?)\s?[\d]{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?"
    r"|(?:desde|aprox\.?|alrededor de)\s+\$?\s?[\d]{1,6}"
    r"|[\d]{1,4}\s*(?:USD|dólares|euros)/?(?:mes|hora|sesión)?",
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


def _name_appears_in_source(name: str, src: dict[str, Any]) -> bool:
    blob = f"{src.get('title') or ''} {src.get('snippet') or ''}"
    return name.lower() in blob.lower()


def _is_plausible_competitor_name(name: str) -> bool:
    n = (name or "").strip()
    if len(n) < 3 or len(n) > 60:
        return False
    if _GENERIC_NAME_BLOCK.match(n):
        return False
    # Reject pure geography / single common nouns without brand signal
    words = n.split()
    if len(words) == 1 and n.islower():
        return False
    if re.fullmatch(r"[\d\W]+", n):
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

    import json

    prompt = (
        "Extrae hasta 3 competidores o comparables REALES del negocio descrito. "
        "SOLO nombres que aparezcan literalmente en title/snippet de las fuentes. "
        "Si no hay nombres de empresas/marcas claros, devuelve lista vacía. "
        "NO inventes. JSON: {\"competitors\":[{\"name\":\"...\",\"note\":\"una linea\","
        "\"source_index\":0}]}\n"
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
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "name": name,
                "note": note or (src.get("snippet") or "")[:160],
                "source": {
                    "title": src.get("title"),
                    "url": src.get("url"),
                    "query": src.get("query"),
                    "snippet": (src.get("snippet") or "")[:200],
                },
            }
        )
        if len(out) >= 3:
            break
    return out


def _extract_competitors_heuristic(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fallback: títulos de páginas con URL, filtrando genéricos."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for src in sources:
        if (src.get("purpose") or "") not in ("competitors", "comparables"):
            continue
        url = str(src.get("url") or "").strip()
        if not url:
            continue
        title = str(src.get("title") or "").strip()
        name = re.split(r"\s+[|\-–:]\s+", title, maxsplit=1)[0].strip()
        if not _is_plausible_competitor_name(name):
            continue
        # Prefer multi-word brand-like titles
        if len(name.split()) < 2 and not re.search(r"[A-Z]{2,}|\d", name):
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "name": name,
                "note": (src.get("snippet") or title)[:160],
                "source": {
                    "title": title,
                    "url": url,
                    "query": src.get("query"),
                    "snippet": (src.get("snippet") or "")[:200],
                },
            }
        )
        if len(out) >= 3:
            break
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

        if purpose == "pricing" or _PRICEISH.search(snippet):
            for pm in _PRICEISH.finditer(snippet):
                prices.append(
                    {
                        "text": pm.group(0).strip(),
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
