"""Jerarquía de conocimiento v38 — LEVEL-1 interno, LEVEL-2 GPT, LEVEL-3 web."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.services.cognitive_intents import (
    is_internal_knowledge_query,
    is_web_research_intent,
    requires_live_web,
)
from app.services.internal_knowledge import (
    InternalKnowledgeHit,
    best_internal_answer,
    format_hits_for_prompt,
    should_use_internal_brain,
)

logger = logging.getLogger(__name__)

KB_CONFIDENCE_THRESHOLD = 0.70


def _prefers_web_search(query: str) -> bool:
    if requires_live_web(query):
        return True
    return is_web_research_intent(query) and not is_internal_knowledge_query(query)


@dataclass(frozen=True)
class KnowledgeRoute:
    level: str
    inject: str | None
    module: str | None
    confidence: float | None
    use_web: bool


def route_knowledge(
    user_text: str,
    *,
    kb_hits: list[InternalKnowledgeHit] | None = None,
) -> KnowledgeRoute:
    """Determina nivel de conocimiento y contexto a inyectar."""
    query = (user_text or "").strip()
    if not query:
        return KnowledgeRoute("LEVEL-2", None, None, None, False)

    hit: InternalKnowledgeHit | None = None
    if kb_hits:
        hit = kb_hits[0] if kb_hits else None
    else:
        hit = best_internal_answer(query)
    if hit and should_use_internal_brain(query, hit) and not _prefers_web_search(query):
        confidence = float(hit.confidence or 0.0)
        if confidence >= KB_CONFIDENCE_THRESHOLD or is_internal_knowledge_query(query):
            module = str(getattr(hit, "domain", None) or hit.domain_label or "internal")
            submodule = str(hit.title or "")
            inject = format_hits_for_prompt([hit])
            logger.info(
                "[LEVEL-1] knowledge_internal module=%s submodule=%s confidence=%.2f",
                module,
                submodule or "-",
                confidence,
            )
            logger.info(
                "[KB-MATCH] module=%s submodule=%s confidence=%.2f",
                module,
                submodule or "-",
                confidence,
            )
            return KnowledgeRoute("LEVEL-1", inject, module, confidence, False)

    if _prefers_web_search(query):
        logger.info("[LEVEL-3] web_search query=%s", query[:120])
        return KnowledgeRoute("LEVEL-3", None, None, None, True)

    logger.info("[LEVEL-2] gpt41_native query=%s", query[:120])
    return KnowledgeRoute("LEVEL-2", None, None, None, False)


def level_system_overlay(route: KnowledgeRoute) -> str:
    if route.level == "LEVEL-1" and route.inject:
        return (
            f"Contexto conocimiento interno CED (NIVEL 1 — prioridad máxima):\n{route.inject}\n"
            "Responde desde este contexto. PROHIBIDO invocar search_web salvo dato en tiempo real."
        )
    if route.level == "LEVEL-3":
        return (
            "NIVEL 3 — Este tema requiere datos en tiempo real. "
            "Invoca search_web si necesitas información actual."
        )
    return (
        "NIVEL 2 — Responde con tu razonamiento nativo. "
        "NO invoques search_web para opiniones, conceptos estables ni charla."
    )
