"""Router cognitivo híbrido — cerebro interno + web + sistema avanzado + memoria."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from app.services.cognitive_intents import (
    CognitiveIntent,
    analyze_intent,
    is_volatile_query,
)
from app.services.cognitive_memory import memory_context_for_voice, save_memory, search_memory
from app.services.claude_deep_analysis import consultar_sistema_avanzado
from app.services.gemini_grounded import fetch_voice_brief
from app.services.internal_knowledge import (
    format_hits_for_prompt,
    search_internal_knowledge,
    should_use_internal_brain,
)
from app.services.search_orchestrator import run_panel_search

logger = logging.getLogger(__name__)

Channel = Literal["voice", "text"]


@dataclass
class CognitiveRouteResult:
    intent: str
    channel: str
    confidence: float
    domain_id: str | None = None
    domain_label: str | None = None
    web_kind: str | None = None
    speakable: str | None = None
    context_for_llm: str | None = None
    needs_advanced_confirm: bool = False
    advanced_prompt: str | None = None
    memory_saved: bool = False
    source: str | None = None
    internal_hits: list[dict[str, Any]] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _memory_context(user_id: str, query: str) -> str:
    data = search_memory(user_id, query, limit=3)
    items = data.get("results") or []
    if not items:
        recent = search_memory(user_id, "", limit=3).get("results") or []
        items = recent
    if not items:
        return ""
    lines = [f"- {i['key']}: {i['content'][:200]}" for i in items]
    return "Memorias del usuario relevantes:\n" + "\n".join(lines)


def _schedule_panel_search(user_id: str, query: str) -> None:
    import threading

    def _run() -> None:
        try:
            asyncio.run(run_panel_search(user_id, query))
        except Exception:  # noqa: BLE001
            pass

    threading.Thread(target=_run, daemon=True).start()


def route_message(
    user_id: str,
    text: str,
    *,
    channel: Channel = "text",
    confirm_pending: bool = False,
    execute_side_effects: bool = True,
) -> CognitiveRouteResult:
    """Decide cómo responder sin adivinar: interno → web → avanzado."""
    raw = (text or "").strip()
    if not raw:
        return CognitiveRouteResult(
            intent=CognitiveIntent.DIRECT_REPLY.value,
            channel=channel,
            confidence=0.0,
            speakable="No recibí la consulta.",
        )

    analysis = analyze_intent(raw, confirm_pending=confirm_pending)

    if analysis.primary == CognitiveIntent.MEMORY_SAVE and analysis.memory_save_text:
        if execute_side_effects:
            save_memory(user_id, "nota_voz" if channel == "voice" else "nota_chat", analysis.memory_save_text)
        return CognitiveRouteResult(
            intent=analysis.primary.value,
            channel=channel,
            confidence=1.0,
            speakable="Guardado en memoria cognitiva.",
            memory_saved=True,
        )

    if analysis.primary == CognitiveIntent.MEMORY_RECALL:
        ctx = _memory_context(user_id, raw)
        return CognitiveRouteResult(
            intent=analysis.primary.value,
            channel=channel,
            confidence=0.9 if ctx else 0.3,
            context_for_llm=ctx or "No encontré memorias sobre eso todavía.",
            speakable=None,
        )

    if analysis.primary == CognitiveIntent.META_PUBLISH:
        return CognitiveRouteResult(
            intent=analysis.primary.value,
            channel=channel,
            confidence=1.0,
            context_for_llm="El usuario quiere publicar en redes. Usa herramientas Meta si están conectadas.",
            meta={"hint": "meta_tools"},
        )

    if analysis.primary == CognitiveIntent.WEB_SEARCH:
        brief = fetch_voice_brief(raw, kind=analysis.web_kind)
        if execute_side_effects and channel == "voice":
            _schedule_panel_search(user_id, raw)
        if brief.get("ok"):
            summary = str(brief.get("summary") or "")
            return CognitiveRouteResult(
                intent=CognitiveIntent.WEB_SEARCH.value,
                channel=channel,
                confidence=0.95,
                web_kind=analysis.web_kind,
                speakable=summary,
                context_for_llm=f"Información verificada en web ({brief.get('source', 'web')}):\n{summary}",
                source=str(brief.get("source") or "web"),
            )
        return CognitiveRouteResult(
            intent=CognitiveIntent.WEB_SEARCH.value,
            channel=channel,
            confidence=0.2,
            web_kind=analysis.web_kind,
            speakable=str(brief.get("error") or "No pude buscar en internet ahora."),
        )

    if analysis.primary == CognitiveIntent.ADVANCED_ANALYSIS:
        if analysis.needs_advanced_confirm:
            return CognitiveRouteResult(
                intent=CognitiveIntent.ADVANCED_ANALYSIS.value,
                channel=channel,
                confidence=0.5,
                needs_advanced_confirm=True,
                advanced_prompt=raw,
                speakable="¿Quieres que consulte al sistema avanzado? Confirma con un sí.",
            )
        if execute_side_effects:
            deep = consultar_sistema_avanzado(raw)
            if deep.get("ok"):
                result = str(deep.get("result") or "")
                return CognitiveRouteResult(
                    intent=CognitiveIntent.ADVANCED_ANALYSIS.value,
                    channel=channel,
                    confidence=0.92,
                    speakable=result,
                    context_for_llm=result,
                    source="advanced_system",
                )
            return CognitiveRouteResult(
                intent=CognitiveIntent.ADVANCED_ANALYSIS.value,
                channel=channel,
                confidence=0.2,
                speakable=str(deep.get("error") or "El sistema avanzado no respondió."),
            )
        return CognitiveRouteResult(
            intent=CognitiveIntent.ADVANCED_ANALYSIS.value,
            channel=channel,
            confidence=0.8,
            advanced_prompt=raw,
            needs_advanced_confirm=False,
        )

    # Cerebro interno (estable) — fluidez sin cargar internet
    hits = search_internal_knowledge(raw, limit=3)
    hit = hits[0] if hits else None
    mem_ctx = _memory_context(user_id, raw)
    volatile = is_volatile_query(raw)

    if hit and should_use_internal_brain(raw, hit) and not volatile:
        ctx = format_hits_for_prompt(hits)
        if mem_ctx:
            ctx = mem_ctx + "\n\n" + ctx
        return CognitiveRouteResult(
            intent=CognitiveIntent.INTERNAL_KNOWLEDGE.value,
            channel=channel,
            confidence=hit.confidence,
            domain_id=hit.domain_id,
            domain_label=hit.domain_label,
            context_for_llm=ctx,
            internal_hits=[asdict(h) for h in hits],
            source="internal_brain",
            meta={"fast_path": True},
        )

    if volatile and not analysis.needs_web:
        brief = fetch_voice_brief(raw, kind="general")
        if brief.get("ok"):
            summary = str(brief.get("summary") or "")
            return CognitiveRouteResult(
                intent=CognitiveIntent.WEB_SEARCH.value,
                channel=channel,
                confidence=0.85,
                web_kind="general",
                speakable=summary,
                context_for_llm=f"Dato sensible al tiempo — verificado en web:\n{summary}",
                source="web_fallback",
            )

    # Respuesta directa con contexto parcial interno + memoria
    partial = format_hits_for_prompt(hits[:1]) if hits else ""
    ctx_parts = [p for p in (mem_ctx, partial) if p]
    ctx = "\n\n".join(ctx_parts) if ctx_parts else None
    domain = hit.domain_id if hit else None
    label = hit.domain_label if hit else None

    return CognitiveRouteResult(
        intent=CognitiveIntent.DIRECT_REPLY.value,
        channel=channel,
        confidence=hit.confidence if hit else 0.45,
        domain_id=domain,
        domain_label=label,
        context_for_llm=ctx,
        internal_hits=[asdict(h) for h in hits],
        source="direct",
    )


def build_voice_system_extras(user_id: str) -> str:
    """Inyectar al token Live: memoria + política del cerebro híbrido."""
    mem = memory_context_for_voice(user_id)
    policy = (
        "Política CED: responde directo si el tema es estable (conceptos, historia, negocio general). "
        "Usa búsqueda web solo para clima, noticias, precios o datos de hoy. "
        "Sistema avanzado solo tras UNA confirmación del usuario para análisis profundo. "
        "Si ya confirmó, ejecuta sin volver a preguntar."
    )
    parts = [policy]
    if mem:
        parts.append(mem)
    return "\n\n".join(parts)


def build_chat_system_extras(user_id: str, routed: CognitiveRouteResult | None = None) -> str:
    mem = memory_context_for_voice(user_id)
    parts = [
        "CED usa cerebro interno premium por ramas + web solo cuando el dato cambia en el tiempo. "
        "No digas que no tienes internet si puedes usar contexto inyectado o herramientas.",
    ]
    if mem:
        parts.append(mem)
    if routed and routed.context_for_llm:
        parts.append(routed.context_for_llm)
    if routed and routed.needs_advanced_confirm:
        parts.append(
            "El usuario pidió análisis profundo. Pregunta si desea activar el sistema avanzado antes de profundizar."
        )
    return "\n\n".join(parts)
