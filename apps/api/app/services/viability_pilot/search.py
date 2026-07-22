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
    r"suplemento|supplement|vitamina|col[aá]geno|prote[ií]na|"
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
    profile: dict[str, str] | None = None,
) -> list[dict[str, str]]:
    """Consultas ancladas a categoría/uso — no a sabor/formato suelto."""
    topic = (offering or "").strip()[:180]
    if not topic:
        return []
    loc = (region or "").strip()[:80]
    cat_hint = (category_hint or "").strip()[:80]
    focus = (profile or {}).get("search_focus") or topic
    category = (profile or {}).get("category") or cat_hint
    use_case = (profile or {}).get("use_case") or ""

    # Competitor queries: categoría + uso, no la descripción completa con distractores
    rival_core = focus
    if category and category.lower() not in focus.lower():
        rival_core = f"{category} {focus}".strip()
    rival_core = rival_core[:140]
    loc_suffix = f" {loc}" if loc else ""
    use_bit = ""
    if use_case:
        # Keep use short — avoid dumping full sentence into query
        short_use = re.split(r"[.]", use_case)[0].strip()[:60]
        if short_use.lower() not in rival_core.lower():
            use_bit = f" {short_use}"
    english = _prefer_english_queries(f"{rival_core} {topic}", loc)

    if english:
        return [
            {
                "purpose": "competitors",
                "query": (
                    f"direct competitors to {rival_core}{use_bit} "
                    f"same category alternatives{loc_suffix}"
                ).strip(),
            },
            {
                "purpose": "pricing",
                "query": f"{rival_core} typical price USD buy{loc_suffix}".strip(),
            },
            {
                "purpose": "trends",
                "query": (
                    f"{category or rival_core} market trends 2025 2026 demand{loc_suffix}"
                ).strip(),
            },
            {
                "purpose": "comparables",
                "query": (
                    f"{rival_core} vs competing brands same use case comparison{loc_suffix}"
                ).strip(),
            },
        ][:MAX_QUERIES]

    return [
        {
            "purpose": "competitors",
            "query": (
                f"competidores directos de {rival_core}{use_bit} "
                f"misma categoria alternativas{loc_suffix}"
            ).strip(),
        },
        {
            "purpose": "pricing",
            "query": f"{rival_core} precio típico cuánto cuesta{loc_suffix}".strip(),
        },
        {
            "purpose": "trends",
            "query": (
                f"{category or rival_core} tendencias mercado 2025 2026 demanda{loc_suffix}"
            ).strip(),
        },
        {
            "purpose": "comparables",
            "query": (
                f"{rival_core} vs marcas competencia mismo uso comparación{loc_suffix}"
            ).strip(),
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
    *,
    profile: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Competidores directos (misma categoría/uso) — no coincidencia por sabor/formato."""
    from app.config import get_settings

    api_key = get_settings().google_api_key.strip()
    if not api_key or not sources:
        return []

    # Prefer competitor/comparable sources for extraction
    ranked = sorted(
        sources,
        key=lambda s: 0 if (s.get("purpose") or "") in ("competitors", "comparables") else 1,
    )
    indexed = []
    for i, src in enumerate(ranked[:16]):
        indexed.append(
            {
                "i": i,
                "purpose": src.get("purpose"),
                "title": (src.get("title") or "")[:120],
                "url": (src.get("url") or "")[:200],
                "snippet": (src.get("snippet") or "")[:320],
            }
        )
    # Map ranked index back to original sources list for validation
    ranked_sources = ranked[:16]

    profile = profile or {}
    category = profile.get("category") or ""
    use_case = profile.get("use_case") or ""
    focus = profile.get("search_focus") or offering[:120]

    prompt = (
        "Eres analista de competencia. Extrae hasta 3 COMPETIDORES DIRECTOS del producto.\n"
        "REGLAS ESTRICTAS:\n"
        "1) Un competidor debe servir el MISMO uso/categoría (sustituto real que el "
        "cliente compararía al comprar). Ej: dos fibras solubles sí; fibra vs colágeno NO.\n"
        "2) PROHIBIDO elegir marcas solo porque comparten sabor (naranja), formato "
        "(polvo/cápsulas), o la palabra genérica 'suplemento'.\n"
        "3) El nombre DEBE aparecer literalmente en title/snippet de una fuente.\n"
        "4) Si en las fuentes no hay competidores claros del mismo uso, devuelve lista vacía.\n"
        "5) NO inventes.\n"
        'JSON: {"competitors":[{"name":"...","competition_basis":"mismo uso: ...",'
        '"note":"una linea desde la fuente","source_index":0,"confidence":"high|medium"}]}\n'
        f"Producto (focus): {focus}\n"
        f"Categoría esperada: {category or '(inferir de la oferta)'}\n"
        f"Uso esperado: {use_case or '(inferir de la oferta)'}\n"
        f"Oferta original: {offering[:400]}\n"
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
                temperature=0.05,
                max_output_tokens=900,
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
        basis = str(row.get("competition_basis") or "").strip()[:180]
        confidence = str(row.get("confidence") or "medium").strip().lower()
        try:
            idx = int(row.get("source_index"))
        except (TypeError, ValueError):
            continue
        if idx < 0 or idx >= len(ranked_sources):
            continue
        src = ranked_sources[idx]
        if not _is_plausible_competitor_name(name):
            continue
        if not _name_appears_in_source(name, src):
            alt = next((s for s in sources if _name_appears_in_source(name, s)), None)
            if not alt:
                continue
            src = alt
        if confidence == "low":
            continue
        if not basis or not _basis_looks_direct(basis):
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
                "snippet": (src.get("snippet") or "")[:200],
            },
            sources,
        )
        combined_note = note or (src.get("snippet") or "")[:160]
        if basis and basis.lower() not in combined_note.lower():
            combined_note = f"{basis}. {combined_note}"[:180]
        out.append(
            {
                "name": name,
                "note": combined_note,
                "competition_basis": basis,
                "source": cite,
            }
        )
        if len(out) >= 3:
            break

    return _filter_direct_competitors(offering, out, profile=profile)


def _basis_looks_direct(basis: str) -> bool:
    """Reject bases that only cite surface attributes."""
    b = (basis or "").strip().lower()
    if len(b) < 12:
        return False
    # Explicit surface-only competition claims
    if re.search(
        r"\b(mismo|same|compart[ei]|shares?)\s+"
        r"(sabor|flavor|flavour|formato|format|color|empaque|packaging|"
        r"naranja|orange|polvo|powder)\b",
        b,
    ):
        return False
    surface = re.search(
        r"\b(sabor|flavor|naranja|orange|polvo|powder|c[aá]psula|capsule|"
        r"color|empaque|packaging)\b",
        b,
    )
    substantive = re.search(
        r"\b(categor|uso\b|use\s*case|sustitut|alternative to|compite|compet|"
        r"fibra|fiber|col[aá]geno|prote[ií]na|pre-?entren|vitamina|digest|"
        r"inmun|energ[ií]a|caf[eé]|servicio|tr[aá]nsito|bowel|psyllium)\b",
        b,
    )
    if surface and not substantive:
        return False
    return bool(substantive or re.search(r"\b(mismo uso|same use|misma categor)", b))


def _filter_direct_competitors(
    offering: str,
    competitors: list[dict[str, Any]],
    *,
    profile: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Segunda pasada: descarta marcas que solo comparten vocabulario superficial."""
    if not competitors:
        return []
    from app.config import get_settings

    api_key = get_settings().google_api_key.strip()
    if not api_key:
        return competitors

    profile = profile or {}
    payload = {
        "offering": offering[:400],
        "category": profile.get("category"),
        "use_case": profile.get("use_case"),
        "candidates": [
            {
                "name": c.get("name"),
                "note": c.get("note"),
                "competition_basis": c.get("competition_basis"),
            }
            for c in competitors
        ],
    }
    prompt = (
        "Filtra candidatos a competidor DIRECTO. Conserva solo marcas/productos que "
        "un comprador compararía como sustituto del MISMO uso/categoría.\n"
        "RECHAZA si la única similitud es sabor (naranja), formato (polvo) o la palabra "
        "'suplemento' genérica.\n"
        "Devuelve JSON: {\"keep\":[\"Name Exacto\", ...]} usando nombres exactos de "
        "candidates. Si ninguno sirve, keep=[].\n"
        f"{json.dumps(payload, ensure_ascii=False)[:5000]}"
    )
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.0,
                max_output_tokens=300,
                response_mime_type="application/json",
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        text = (getattr(response, "text", None) or "").strip()
        data = json.loads(text) if text else {}
        keep = data.get("keep") if isinstance(data, dict) else None
        if not isinstance(keep, list):
            return competitors
        keep_l = {str(x).strip().lower() for x in keep if str(x).strip()}
        filtered = [c for c in competitors if (c.get("name") or "").lower() in keep_l]
        logger.info(
            "[VIABILITY-PILOT] relevance filter in=%s out=%s",
            len(competitors),
            len(filtered),
        )
        return filtered
    except Exception:  # noqa: BLE001
        logger.warning("[VIABILITY-PILOT] relevance filter skipped", exc_info=True)
        return competitors


def _extract_competitors_heuristic(
    sources: list[dict[str, Any]],
    *,
    profile: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Fallback conservador: solo listas explícitas de alternativas/competidores."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    focus = ((profile or {}).get("search_focus") or "").lower()

    listish = re.compile(
        r"(?:"
        r"direct\s+competitors?\s+(?:include|are|of)|"
        r"competitors?\s+(?:include|are)|"
        r"alternatives?\s+to[^:]{0,40}:|"
        r"competidores?\s+(?:directos?\s+)?(?:incluyen|son)|"
        r"alternativas?\s+(?:a|de)[^:]{0,40}:"
        r")\s+"
        r"([A-ZÁÉÍÓÚÑ][^.]{8,180})",
        re.I,
    )

    for src in sources:
        if (src.get("purpose") or "") not in ("competitors", "comparables"):
            continue
        snippet = str(src.get("snippet") or "")
        for block in listish.findall(snippet):
            parts = re.split(r",|/|\band\b|\by\b", block)
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
                # Skip if name equals focus product loosely
                if focus and focus in key:
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
                out.append(
                    {
                        "name": name,
                        "note": snippet[:160],
                        "competition_basis": "citado como alternativa/competidor en fuente",
                        "source": cite,
                    }
                )
                if len(out) >= 3:
                    return out
    return out


def extract_attributed_facts(
    sources: list[dict[str, Any]],
    *,
    offering: str = "",
    profile: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Extrae hechos atribuibles — competidores validados por categoría/uso + fuente."""
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
                text = pm.group(0).strip()
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

    competitors = _extract_competitors_llm(offering, sources, profile=profile)
    if len(competitors) < 2:
        for c in _extract_competitors_heuristic(sources, profile=profile):
            if c["name"].lower() in {x["name"].lower() for x in competitors}:
                continue
            competitors.append(c)
            if len(competitors) >= 3:
                break
        if competitors:
            competitors = _filter_direct_competitors(
                offering, competitors, profile=profile
            )

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
