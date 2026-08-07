"""Contexto por módulo para el pipeline unificado de chats cotidianos."""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_MODULE_CONTEXT_RULES = (
    "Responde en español latinoamericano, breve y natural. "
    "Usa SOLO los datos del contexto del módulo; no inventes información."
)


def requires_sync_module_handler(text: str) -> bool:
    """Acciones que deben ejecutarse de forma determinista (escrituras)."""
    from app.modules.finance_module import is_finance_intent, is_finance_write_intent
    from app.services.hud_reminders import is_reminder_intent

    if is_reminder_intent(text) and re.search(r"recu[eé]rdame", text, re.I):
        return True
    if is_finance_intent(text) and is_finance_write_intent(text):
        return True
    return False


def fetch_module_stream_context(
    user_id: str,
    text: str,
) -> tuple[str | None, dict[str, Any] | None]:
    """Obtiene contexto del módulo LIFE/finanzas para inyectar en el system prompt."""
    from app.modules.finance_module import handle_finance_query_sync, is_finance_intent
    from app.services.chat_intents import is_creative_artifact_intent
    from app.services.cognitive_intents import is_news_intent, is_weather_intent
    from app.services.hud_reminders import handle_reminder_query_sync, is_reminder_intent

    if requires_sync_module_handler(text):
        return None, None
    # No inyectar clima cuando el usuario pide imagen o PDF
    # (palabras trampa en el texto citado no son consultas reales al módulo).
    if is_creative_artifact_intent(text):
        return None, None

    try:
        from app.services.opportunities_pilot.fitline_knowledge import (
            format_fitline_knowledge_for_prompt,
            wants_fitline_knowledge,
        )

        if wants_fitline_knowledge(text):
            fitline = format_fitline_knowledge_for_prompt()
            if fitline:
                return (
                    f"{fitline}\n\n{_MODULE_CONTEXT_RULES}",
                    {"intent": "fitline_opportunity", "source": "opportunities_curated"},
                )

        if is_reminder_intent(text):
            spoken = str(handle_reminder_query_sync(user_id, text).get("spoken") or "").strip()
            if spoken:
                return (
                    f"Contexto recordatorios/eventos:\n{spoken}\n\n{_MODULE_CONTEXT_RULES}",
                    {"intent": "reminder_list", "source": "module_context"},
                )

        if is_finance_intent(text):
            spoken = str(handle_finance_query_sync(user_id, text).get("spoken") or "").strip()
            if spoken:
                return (
                    f"Contexto finanzas:\n{spoken}\n\n{_MODULE_CONTEXT_RULES}",
                    {"intent": "finance", "source": "module_context"},
                )

        if is_weather_intent(text):
            from app.services.gemini_grounded import execute_search_web_sync

            web = execute_search_web_sync(text, kind="weather")
            context = str(
                web.get("context_for_llm") or web.get("spoken") or web.get("summary") or ""
            ).strip()
            if context:
                return (
                    f"Contexto clima (datos en vivo):\n{context}\n\n{_MODULE_CONTEXT_RULES}",
                    {"intent": "weather", "source": "web_context"},
                )

        if is_news_intent(text):
            from app.services.gemini_grounded import execute_search_web_sync

            web = execute_search_web_sync(text, kind="news")
            context = str(
                web.get("context_for_llm") or web.get("spoken") or web.get("summary") or ""
            ).strip()
            if context:
                return (
                    f"Contexto noticias (datos en vivo):\n{context}\n\n{_MODULE_CONTEXT_RULES}",
                    {"intent": "news", "source": "web_context"},
                )
    except Exception:  # noqa: BLE001
        logger.exception("[CHAT-MODULE] context fetch failed user=%s", user_id[:8])

    return None, None
