"""Cerebro interno CED — conocimiento estable por ramas (enciclopedia premium)."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.domain.knowledge_domains import KNOWLEDGE_DOMAINS, classify_domain

logger = logging.getLogger(__name__)

_SEED_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "knowledge_seed.json"
_HIGH_CONFIDENCE = 0.82
_MEDIUM_CONFIDENCE = 0.55


@dataclass
class InternalKnowledgeHit:
    domain_id: str
    domain_label: str
    title: str
    summary: str
    confidence: float
    source: str
    article_id: str | None = None


def _load_seed() -> list[dict[str, Any]]:
    if not _SEED_PATH.is_file():
        return []
    try:
        data = json.loads(_SEED_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:  # noqa: BLE001
        logger.warning("[BRAIN] seed load failed")
        return []


def _tokenize(text: str) -> set[str]:
    words = re.findall(r"[a-záéíóúñ0-9]+", (text or "").lower())
    return {w for w in words if len(w) > 2}


def _score_article(query_tokens: set[str], article: dict[str, Any]) -> float:
    title = str(article.get("title") or "")
    summary = str(article.get("summary") or "")
    keywords = article.get("keywords") or []
    blob_tokens = _tokenize(f"{title} {summary} {' '.join(keywords)}")
    if not blob_tokens or not query_tokens:
        return 0.0
    overlap = len(query_tokens & blob_tokens)
    if overlap == 0:
        return 0.0
    base = overlap / max(len(query_tokens), 1)
    title_boost = 0.15 if any(t in title.lower() for t in query_tokens) else 0.0
    return min(1.0, base + title_boost)


def _search_db(query: str, *, limit: int = 3) -> list[dict[str, Any]]:
    try:
        from app.services import supabase_db

        client = supabase_db._client()
        safe = re.sub(r"[%_]", "", query.strip())[:120]
        if not safe:
            return []
        result = (
            client.table("internal_knowledge_articles")
            .select("id, domain, subdomain, title, summary, keywords, source")
            .or_(f"title.ilike.%{safe}%,summary.ilike.%{safe}%")
            .limit(limit)
            .execute()
        )
        return result.data or []
    except Exception:  # noqa: BLE001
        return []


def search_internal_knowledge(query: str, *, limit: int = 3) -> list[InternalKnowledgeHit]:
    """Busca en Supabase + seed local. Primera fuente obligatoria para lo estable."""
    q = (query or "").strip()
    if not q:
        return []

    query_tokens = _tokenize(q)
    domain = classify_domain(q)
    candidates: list[tuple[float, dict[str, Any], str]] = []

    for row in _search_db(q, limit=limit * 2):
        score = _score_article(query_tokens, row)
        if domain and row.get("domain") == domain.id:
            score = min(1.0, score + 0.12)
        candidates.append((score, row, "database"))

    for row in _load_seed():
        score = _score_article(query_tokens, row)
        if domain and row.get("domain") == domain.id:
            score = min(1.0, score + 0.1)
        candidates.append((score, row, "seed"))

    candidates.sort(key=lambda x: x[0], reverse=True)
    hits: list[InternalKnowledgeHit] = []
    seen_titles: set[str] = set()

    for score, row, src in candidates:
        if score < 0.2:
            continue
        title = str(row.get("title") or "")
        if title in seen_titles:
            continue
        seen_titles.add(title)
        dom_id = str(row.get("domain") or "general")
        dom_label = next((d.label for d in KNOWLEDGE_DOMAINS if d.id == dom_id), dom_id)
        hits.append(
            InternalKnowledgeHit(
                domain_id=dom_id,
                domain_label=dom_label,
                title=title,
                summary=str(row.get("summary") or "")[:1200],
                confidence=round(score, 2),
                source=src,
                article_id=str(row.get("id")) if row.get("id") else None,
            )
        )
        if len(hits) >= limit:
            break

    return hits


def best_internal_answer(query: str) -> InternalKnowledgeHit | None:
    hits = search_internal_knowledge(query, limit=1)
    return hits[0] if hits else None


def should_use_internal_brain(query: str, hit: InternalKnowledgeHit | None) -> bool:
    if not hit:
        return False
    domain = classify_domain(query)
    if domain and domain.time_sensitive:
        return False
    return hit.confidence >= _MEDIUM_CONFIDENCE


def format_hits_for_prompt(hits: list[InternalKnowledgeHit]) -> str:
    if not hits:
        return ""
    lines = ["Conocimiento interno CED (priorizar sobre suposiciones):"]
    for h in hits:
        lines.append(f"- [{h.domain_label}] {h.title}: {h.summary}")
    return "\n".join(lines)


def list_domains_public() -> list[dict[str, str]]:
    return [
        {"id": d.id, "label": d.label, "time_sensitive": d.time_sensitive}
        for d in KNOWLEDGE_DOMAINS
    ]
