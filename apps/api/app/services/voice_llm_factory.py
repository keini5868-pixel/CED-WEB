"""Factory del cerebro de voz — Llama local (sin tools) o Gemini (legacy)."""

from __future__ import annotations

from typing import Any, Protocol

from app.services.llama_service import use_llama
from app.services.voice_test_mode import is_gemini_standalone_voice_test


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


def build_voice_llm() -> VoiceLlmProtocol:
    # Usa is_gemini_standalone_voice_test() (no el env crudo): en production el
    # modo standalone se ignora salvo VOICE_STANDALONE_ALLOW_PROD=true.
    if is_gemini_standalone_voice_test():
        from app.services.gemini_voice_standalone import GeminiStandaloneVoiceLlm

        return GeminiStandaloneVoiceLlm()
    if use_llama():
        from app.services.llama_voice_llm import LlamaVoiceLlm

        return LlamaVoiceLlm()
    from app.services.gemini_voice_llm import GeminiVoiceLlm

    return GeminiVoiceLlm()
