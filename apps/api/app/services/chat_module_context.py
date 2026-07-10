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
    from app.modules.calendar_module import is_calendar_intent
    from app.modules.finance_module import is_finance_intent, is_finance_write_intent
    from app.services.hud_reminders import is_reminder_intent

    if is_reminder_intent(text) and re.search(r"recu[eé]rdame", text, re.I):
        return True
    if is_calendar_intent(text) and re.search(
        r"ag[eé]ndame|agendar|programa(?:r|me)|recu[eé]rdame",
        text,
        re.I,
    ):
        return True
    if is_finance_intent(text) and is_finance_write_intent(text):
        return True
    return False


def fetch_module_stream_context(
    user_id: str,
    text: str,
) -> tuple[str | None, dict[str, Any] | None]:
    """Obtiene contexto del módulo LIFE/finanzas para inyectar en el system prompt."""
    from app.modules.calendar_module import handle_calendar_query_sync, is_calendar_intent
    from app.modules.finance_module import handle_finance_query_sync, is_finance_intent
    from app.modules.gmail_module import handle_gmail_query_sync, is_gmail_intent
    from app.services.cognitive_intents import is_news_intent, is_weather_intent
    from app.services.hud_reminders import handle_reminder_query_sync, is_reminder_intent

    if requires_sync_module_handler(text):
        return None, None

    try:
        if is_reminder_intent(text):
            spoken = str(handle_reminder_query_sync(user_id, text).get("spoken") or "").strip()
            if spoken:
                return (
                    f"Contexto recordatorios/eventos:\n{spoken}\n\n{_MODULE_CONTEXT_RULES}",
                    {"intent": "reminder_list", "source": "module_context"},
                )

        if is_calendar_intent(text):
            spoken = str(handle_calendar_query_sync(user_id, text).get("spoken") or "").strip()
            if spoken:
                return (
                    f"Contexto calendario:\n{spoken}\n\n{_MODULE_CONTEXT_RULES}",
                    {"intent": "calendar", "source": "module_context"},
                )

        if is_gmail_intent(text):
            spoken = str(handle_gmail_query_sync(user_id, text).get("spoken") or "").strip()
            if spoken:
                return (
                    f"Contexto Gmail:\n{spoken}\n\n{_MODULE_CONTEXT_RULES}",
                    {"intent": "gmail", "source": "module_context"},
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
