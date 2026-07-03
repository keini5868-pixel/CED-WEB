"""Router cognitivo híbrido — cerebro interno + web + sistema avanzado + memoria."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from app.services.cognitive_intents import (
    CognitiveIntent,
    analyze_intent,
    is_internal_knowledge_query,
    is_web_research_intent,
    requires_live_web,
)
from app.services.cognitive_memory import memory_context_for_voice, save_memory, search_memory
from app.services.gemini_grounded import execute_search_web_sync
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

    hits = search_internal_knowledge(raw, limit=3)
    hit = hits[0] if hits else None
    mem_ctx = _memory_context(user_id, raw)

    prefers_web = requires_live_web(raw) or (
        is_web_research_intent(raw) and not is_internal_knowledge_query(raw)
    ) or analysis.primary == CognitiveIntent.WEB_SEARCH

    if hit and should_use_internal_brain(raw, hit) and not prefers_web:
        ctx = format_hits_for_prompt(hits)
        if mem_ctx:
            ctx = f"{mem_ctx}\n\n{ctx}"
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

    if analysis.primary == CognitiveIntent.WEB_SEARCH:
        brief = execute_search_web_sync(raw, kind=analysis.web_kind or "general")
        if execute_side_effects and channel == "voice":
            _schedule_panel_search(user_id, raw)
        if brief.get("ok"):
            summary = str(brief.get("summary") or brief.get("message") or "")
            return CognitiveRouteResult(
                intent=CognitiveIntent.WEB_SEARCH.value,
                channel=channel,
                confidence=0.95,
                web_kind=analysis.web_kind,
                speakable=summary,
                context_for_llm=f"Información verificada en web ({brief.get('source', 'web')}):\n{summary}",
                source=str(brief.get("source") or "web"),
            )
        fallback_msg = str(
            brief.get("message")
            or brief.get("error")
            or "No pude buscar en internet ahora."
        )
        return CognitiveRouteResult(
            intent=CognitiveIntent.WEB_SEARCH.value,
            channel=channel,
            confidence=0.2,
            web_kind=analysis.web_kind,
            speakable=fallback_msg,
            context_for_llm=(
                "La búsqueda web falló o agotó tiempo. Responde con conocimiento integrado "
                f"y avisa honestamente. Detalle: {fallback_msg}"
            ),
            source="fallback",
            meta={"fallback": True, "status": brief.get("status")},
        )

    # Guiones, estrategia y análisis los responde Gemini directamente (sin sistema avanzado).
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


def voice_platform_awareness_context(user_id: str) -> str:
    """Consciencia de datos disponibles — memoria, cerebro interno, prospección."""
    try:
        from app.domain.knowledge_domains import KNOWLEDGE_DOMAINS
        from app.services.prospection import get_prospection_status

        domain_n = len(KNOWLEDGE_DOMAINS)
        lines = [
            "# CONSCIENCIA CED — INFORMACION DISPONIBLE EN ESTA SESION",
            "Tienes acceso real a:",
            f"- Cerebro interno: {domain_n}+ ramas + articulos Supabase + seed premium.",
            "- Memorias del usuario y contexto de sesiones anteriores (bloques inyectados abajo).",
            "- Conocimiento viral 2026 (Instagram, hooks, Meta) en tu prompt base.",
            "- Herramientas: recall_memory, recall_previous_conversations, save_to_long_term_memory.",
            "- Prospeccion Instagram: activar_prospeccion, reporte_prospeccion.",
            "- Usa recall_memory antes de decir que no recuerdas. reporte_prospeccion para leads.",
            "- NO recites todo el inventario salvo que pregunten que sabes o que datos tienes.",
        ]
        try:
            status = get_prospection_status(user_id)
            if status.get("enabled"):
                lines.append(
                    f"- Prospeccion ACTIVA: {status.get('leads_today', 0)} leads hoy, "
                    f"{status.get('hot_leads', 0)} calientes."
                )
                for lead in status.get("recent") or []:
                    handle = str(lead.get("handle") or "?").lstrip("@")
                    score = lead.get("score", 0)
                    hot = " (caliente)" if lead.get("is_hot") else ""
                    lines.append(f"  - @{handle} score {score}{hot}")
            else:
                lines.append("- Prospeccion: desactivada (activar_prospeccion si la piden).")
        except Exception:  # noqa: BLE001
            lines.append("- Prospeccion: usa reporte_prospeccion si preguntan por leads.")
        return "\n".join(lines)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[VOICE] awareness context fallback: %s", exc)
        return (
            "# CONSCIENCIA CED\n"
            "Tienes memoria, cerebro interno, prospeccion y herramientas recall_memory / reporte_prospeccion."
        )


def build_voice_system_extras(user_id: str) -> str:
    """Inyectar al token Live: tratamiento, memoria + política + estado Meta."""
    from app.services import supabase_db
    from app.services.user_address import address_context_for_prompt

    address = address_context_for_prompt(user_id)
    policy = (
        "Política CED: responde directo si el tema es estable (conceptos, historia, negocio general). "
        "Usa búsqueda web solo para clima, noticias, precios o datos de hoy. "
        "Sistema avanzado solo tras UNA confirmación del usuario para análisis profundo. "
        "Si ya confirmó, ejecuta sin volver a preguntar. "
        "Cámara apagada por defecto: no afirmes visión. Visión solo vía analyze_camera_frame o buscar_lo_visible."
    )
    conn = supabase_db.get_meta_connection(user_id)
    if conn and conn.get("access_token"):
        username = conn.get("ig_username") or "Meta"
        meta = (
            f"Estado Meta del usuario: CONECTADO (@{username}). "
            "Puedes publicar en Facebook e Instagram con publicar_facebook / publicar_instagram. "
            "Cuando confirmen el texto del post, INVOCA la herramienta de inmediato — no simules. "
            "PROHIBIDO decir 'estoy revisando' sin ejecutar la tool. "
            "Si falla por permisos, pide reconectar Meta en Conectar Redes."
        )
    else:
        meta = (
            "Estado Meta del usuario: NO conectado. "
            "Puedes redactar posts pero NO digas que publicaste. "
            "Indica conectar Meta en el dashboard → Conectar Redes."
        )
    parts = [address, voice_platform_awareness_context(user_id), policy, meta]
    try:
        mem = memory_context_for_voice(user_id, limit=8)
    except Exception:  # noqa: BLE001
        mem = ""
    if mem:
        parts.append(mem)
    try:
        from app.services.conversation_memory import load_user_context

        ctx = load_user_context(user_id)
        if ctx:
            parts.append(ctx)
    except Exception:  # noqa: BLE001
        pass
    return "\n\n".join(parts)


def build_chat_system_extras(user_id: str, routed: CognitiveRouteResult | None = None) -> str:
    from app.services.user_address import address_context_for_prompt

    mem = memory_context_for_voice(user_id)
    parts = [
        address_context_for_prompt(user_id),
        "CED usa cerebro interno premium por ramas + web solo cuando el dato cambia en el tiempo. "
        "No digas que no tienes internet si puedes usar contexto inyectado o herramientas.",
    ]
    if mem:
        parts.append(mem)
    try:
        from app.services.conversation_memory import load_user_context

        ctx = load_user_context(user_id)
        if ctx:
            parts.append(ctx)
    except Exception:  # noqa: BLE001
        pass
    if routed and routed.context_for_llm:
        ctx = routed.context_for_llm
        if "Conocimiento interno CED" in ctx:
            ctx = (
                "CONTEXTO INTERNO DEL SISTEMA (NO mostrar al usuario — solo usar para redactar):\n"
                f"{ctx}"
            )
        parts.append(ctx)
    return "\n\n".join(parts)
