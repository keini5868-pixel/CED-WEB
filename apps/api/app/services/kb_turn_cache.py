"""Cache de KB por turno — evita búsquedas duplicadas en el mismo mensaje."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.internal_knowledge import InternalKnowledgeHit

_CACHE: dict[int, tuple[float, list[InternalKnowledgeHit]]] = {}
_TTL_SEC = 45.0
_MAX_ENTRIES = 128


def _cache_key(query: str) -> int:
    normalized = " ".join((query or "").strip().lower().split())
    return hash(normalized)


def get_turn_kb_hits(query: str, *, limit: int = 2) -> list:
    from app.services.internal_knowledge import search_internal_knowledge

    key = _cache_key(query)
    now = time.time()
    cached = _CACHE.get(key)
    if cached and (now - cached[0]) < _TTL_SEC:
        return list(cached[1][:limit])

    hits = search_internal_knowledge(query, limit=limit)
    _CACHE[key] = (now, hits)
    if len(_CACHE) > _MAX_ENTRIES:
        oldest = sorted(_CACHE.items(), key=lambda item: item[1][0])[: len(_CACHE) - _MAX_ENTRIES]
        for stale_key, _ in oldest:
            _CACHE.pop(stale_key, None)
    return hits


def clear_turn_kb_cache() -> None:
    _CACHE.clear()
