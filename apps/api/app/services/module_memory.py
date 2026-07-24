"""Memoria modular on-demand — carga SOLO al activar un módulo.

Cada módulo con datos persistentes registra un loader que devuelve un bloque de
contexto compacto para inyectar en el overlay del módulo. No se precarga nada en
la conversación base neutral.

Uso previsto (Fase 3): al activar un módulo, el orquestador llama
`load_module_memory(module, user_id)` y añade el resultado al system prompt del
módulo. Hasta entonces este módulo es autónomo y testeable.
"""

from __future__ import annotations

import logging
from typing import Callable

logger = logging.getLogger(__name__)

ModuleMemoryLoader = Callable[[str], str | None]

# Módulos que pueden tener memoria persistente on-demand.
MODULES_WITH_MEMORY: frozenset[str] = frozenset(
    {
        "finance",
        "memory",
        "stripe",
    }
)


def _load_finance_memory(user_id: str) -> str | None:
    from app.services.finance_ledger import (
        format_pending_spoken,
        format_summary_spoken,
        list_pending_payments,
        summarize_finances,
    )

    try:
        this_month = summarize_finances(user_id, period="mes")
        last_month = summarize_finances(user_id, period="mes_pasado")
    except Exception:  # noqa: BLE001
        logger.warning("[MODULE_MEM] finance load failed user=%s", user_id[:8])
        return None

    lines = ["# MEMORIA FINANZAS (datos reales — no inventar cifras)"]
    lines.append("- " + format_summary_spoken(this_month))
    if last_month.get("count"):
        lines.append("- Mes pasado: " + format_summary_spoken(last_month))
    try:
        pending = list_pending_payments(user_id)
        if pending:
            lines.append("- Pagos pendientes: " + format_pending_spoken(pending))
    except Exception:  # noqa: BLE001
        pass
    return "\n".join(lines)


def _load_conversation_memory(user_id: str) -> str | None:
    """Memoria de conversaciones previas — solo cuando el módulo 'memory' se activa."""
    parts: list[str] = []
    try:
        from app.services.conversation_memory import load_user_context

        ctx = load_user_context(user_id)
        if ctx:
            parts.append(ctx)
    except Exception:  # noqa: BLE001
        logger.warning("[MODULE_MEM] conversation context failed user=%s", user_id[:8])
    try:
        from app.services.session_memory import get_session_memory_context

        mem_ctx = get_session_memory_context(user_id)
        if mem_ctx:
            parts.append(mem_ctx)
    except Exception:  # noqa: BLE001
        pass
    if not parts:
        return None
    return "\n\n".join(parts)


def _load_stripe_memory(user_id: str) -> str | None:
    try:
        from app.services import supabase_db

        profile = supabase_db.get_profile(user_id) or {}
    except Exception:  # noqa: BLE001
        logger.warning("[MODULE_MEM] stripe/profile load failed user=%s", user_id[:8])
        return None

    plan = str(profile.get("plan") or profile.get("subscription_tier") or "free")
    role = str(profile.get("role") or "")
    lines = [
        "# MEMORIA SUSCRIPCIÓN",
        f"- Plan actual: {plan}",
    ]
    if role:
        lines.append(f"- Rol: {role}")
    return "\n".join(lines)


MEMORY_LOADERS: dict[str, ModuleMemoryLoader] = {
    "finance": _load_finance_memory,
    "memory": _load_conversation_memory,
    "stripe": _load_stripe_memory,
}


def has_module_memory(module: str) -> bool:
    return module in MEMORY_LOADERS


def load_module_memory(module: str, user_id: str) -> str | None:
    """Carga la memoria persistente de un módulo. None si no aplica o falla."""
    loader = MEMORY_LOADERS.get((module or "").strip())
    uid = (user_id or "").strip()
    if not loader or not uid:
        return None
    try:
        block = loader(uid)
        if block and block.strip():
            return block.strip()
    except Exception:  # noqa: BLE001
        logger.exception("[MODULE_MEM] loader failed module=%s user=%s", module, uid[:8])
    return None


def format_module_context(module: str, memory_block: str | None) -> str | None:
    """Envuelve memoria + etiqueta de módulo para inyectar al prompt."""
    if not memory_block:
        return None
    label = module.upper().replace("_", " ")
    return f"# CONTEXTO MÓDULO {label}\n{memory_block}"
