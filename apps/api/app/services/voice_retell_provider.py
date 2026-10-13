"""Proveedor del cerebro Retell Custom LLM (independiente del chat Avanzado)."""

from __future__ import annotations

from app.config import get_settings

_ALIASES = {
    "haiku": "claude",
    "anthropic": "claude",
    "gpt": "openai",
    "openai": "openai",
    "gemini": "gemini",
    "google": "gemini",
    "llama": "llama",
    "ollama": "llama",
}


def normalize_retell_voice_provider(raw: str) -> str:
    key = (raw or "").strip().lower()
    if not key:
        return ""
    return _ALIASES.get(key, key)


def resolve_retell_voice_provider() -> str:
    """RETELL_LLM_PROVIDER gana; si vacío, LLM_PROVIDER; default claude (Haiku)."""
    settings = get_settings()
    explicit = normalize_retell_voice_provider(settings.retell_llm_provider or "")
    if explicit:
        return explicit
    from_llm = normalize_retell_voice_provider(settings.llm_provider or "")
    if from_llm:
        return from_llm
    return "claude"
