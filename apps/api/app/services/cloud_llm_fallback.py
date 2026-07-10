"""Fallback cloud (Claude primero) cuando Llama local falla o no está listo."""

from __future__ import annotations

import logging
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)


def cloud_llm_configured() -> bool:
    settings = get_settings()
    return bool(settings.google_api_key.strip() or settings.anthropic_api_key.strip())


def chat_cloud_reply(
    *,
    system: str,
    messages: list[dict[str, Any]],
    user_text: str = "",
    max_tokens: int = 2048,
) -> str | None:
    """Respuesta no-stream vía Claude (único fallback conversacional)."""
    from app.services.text_chat import (
        CHAT_SIMPLE_MAX_TOKENS,
        _anthropic_simple_reply,
        _gemini_chat_model,
        _gemini_simple_reply,
    )

    settings = get_settings()
    google_key = settings.google_api_key.strip()
    anthropic_key = settings.anthropic_api_key.strip()
    if not google_key and not anthropic_key:
        return None

    token_budget = max_tokens or CHAT_SIMPLE_MAX_TOKENS

    if anthropic_key:
        try:
            return _anthropic_simple_reply(
                api_key=anthropic_key,
                system=system,
                messages=messages,
                max_tokens=token_budget,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[CLOUD-FALLBACK] anthropic failed: %s", exc)

    if google_key:
        logger.warning(
            "[CLOUD-FALLBACK] Sin Claude disponible — fallback Gemini degradado"
        )
        try:
            return _gemini_simple_reply(
                api_key=google_key,
                model=_gemini_chat_model(),
                system=system,
                messages=messages,
                max_tokens=token_budget,
                allow_llama=False,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[CLOUD-FALLBACK] gemini failed: %s", exc)
    return None


def iter_chat_cloud_stream(
    *,
    system: str,
    messages: list[dict[str, Any]],
    max_tokens: int = 2048,
):
    """Streaming cloud — Claude, sin Llama."""
    from app.services.claude_advanced import _iter_anthropic_text_stream

    settings = get_settings()
    anthropic_key = settings.anthropic_api_key.strip()
    if not anthropic_key:
        raise RuntimeError("missing_anthropic_api_key_for_stream")
    for piece, _label in _iter_anthropic_text_stream(
        api_key=anthropic_key,
        system=system,
        messages=messages,
        max_tokens=max_tokens,
        user_text="",
    ):
        if piece:
            yield piece
