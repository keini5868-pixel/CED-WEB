"""Factory del cerebro de voz Retell — Claude Haiku (default), OpenAI, Gemini o Llama local."""

from __future__ import annotations

import logging
from typing import Any, Protocol

from app.config import get_settings
from app.services.llama_service import llama_voice_model_ready
from app.services.voice_retell_provider import resolve_retell_voice_provider
from app.services.voice_test_mode import is_gemini_standalone_voice_test

logger = logging.getLogger(__name__)


class VoiceLlmProtocol(Protocol):
    """Interfaz mínima usada por retell_custom_llm."""

    user_id: str | None

    def set_module_overlay(self, overlay: str | None) -> None: ...
    def set_user_id(self, user_id: str | None) -> None: ...
    def set_latency_context(self, call_id: str, response_id: int) -> None: ...
    def take_deferred_batch(self) -> Any: ...
    async def draft_greeting(self) -> str: ...
    async def draft_reminder(self, transcript: list) -> str: ...
    async def draft_conversational_response(self, request: Any) -> str | None: ...
    def draft_response(self, request: Any) -> Any: ...
    async def generate_natural_reply(self, **kwargs: Any) -> str: ...
    async def generate_empathetic_reformulation(self, **kwargs: Any) -> str | None: ...
    async def apply_deferred_results(self, batch: Any, *, results: list) -> None: ...
    def build_async_tool_payload(self, name: str, tool_args: dict, tool_result: dict) -> tuple[str, dict]: ...


def _anthropic_configured() -> bool:
    return bool((get_settings().anthropic_api_key or "").strip())


def _openai_configured() -> bool:
    from app.services.openai_key_utils import sanitize_openai_api_key

    return bool(sanitize_openai_api_key(get_settings().openai_api_key))


def _gemini_configured() -> bool:
    return bool((get_settings().google_api_key or "").strip())


def build_voice_llm() -> VoiceLlmProtocol:
    if is_gemini_standalone_voice_test():
        from app.services.gemini_voice_standalone import GeminiStandaloneVoiceLlm

        logger.info("[VOICE] brain=gemini_standalone")
        return GeminiStandaloneVoiceLlm()

    provider = resolve_retell_voice_provider()

    if provider == "llama":
        from app.services.llama_voice_llm import LlamaVoiceLlm

        if llama_voice_model_ready():
            logger.info("[VOICE] brain=llama")
            return LlamaVoiceLlm()
        logger.warning("[VOICE] Ollama no listo — eligiendo fallback cloud con tools")
        provider = "claude" if _anthropic_configured() else "openai" if _openai_configured() else "gemini"

    if provider == "openai":
        if not _openai_configured():
            logger.error("[VOICE] RETELL_LLM_PROVIDER=openai pero falta OPENAI_API_KEY")
        from app.services.openai_voice_llm import OpenAIVoiceLlm

        logger.info("[VOICE] brain=openai")
        return OpenAIVoiceLlm()

    if provider == "gemini":
        if not _gemini_configured():
            logger.error("[VOICE] RETELL_LLM_PROVIDER=gemini pero falta GOOGLE_API_KEY")
        from app.services.gemini_voice_llm import GeminiVoiceLlm

        logger.info("[VOICE] brain=gemini")
        return GeminiVoiceLlm()

    if provider == "claude":
        if _anthropic_configured():
            from app.services.claude_voice_llm import ClaudeVoiceLlm

            logger.info("[VOICE] brain=claude-haiku")
            return ClaudeVoiceLlm()
        logger.error(
            "[VOICE] RETELL_LLM_PROVIDER=claude pero falta ANTHROPIC_API_KEY — fallback"
        )
        if _openai_configured():
            from app.services.openai_voice_llm import OpenAIVoiceLlm

            logger.info("[VOICE] brain=openai (fallback sin Anthropic)")
            return OpenAIVoiceLlm()
        from app.services.gemini_voice_llm import GeminiVoiceLlm

        logger.warning("[VOICE] brain=gemini (fallback sin Anthropic/OpenAI)")
        return GeminiVoiceLlm()

    logger.warning("[VOICE] provider=%s desconocido — usando Claude/Gemini", provider)
    if _anthropic_configured():
        from app.services.claude_voice_llm import ClaudeVoiceLlm

        return ClaudeVoiceLlm()
    from app.services.gemini_voice_llm import GeminiVoiceLlm

    return GeminiVoiceLlm()
