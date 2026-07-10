"""Pipeline unificado Llama → Claude → Gemini para chats cotidianos."""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)


def iter_unified_llm_stream(
    *,
    api_key: str,
    model: str,
    system: str,
    messages: list[dict[str, Any]],
    max_tokens: int,
    allow_llama: bool = True,
    user_text: str = "",
) -> Iterator[tuple[str, str]]:
    """Stream de texto con Llama primero y fallback Claude/Gemini.

    Yields (text_piece, model_label).
    """
    from app.services.llama_service import (
        _CHAT_TIMEOUT_SEC,
        iter_llama_chat_stream,
        llama_model,
        should_route_to_llama,
        use_llama,
    )

    if allow_llama and use_llama() and should_route_to_llama(fast_probe=True):
        label = llama_model()
        started = time.monotonic()
        try:
            for piece in iter_llama_chat_stream(
                system=system,
                messages=messages,
                temperature=0.4,
                max_tokens=max_tokens,
            ):
                if time.monotonic() - started > _CHAT_TIMEOUT_SEC:
                    logger.warning(
                        "[CHAT-PIPE] Llama stream timeout %.0fs — fallback Claude",
                        _CHAT_TIMEOUT_SEC,
                    )
                    break
                if piece:
                    yield piece, label
            else:
                return
        except Exception as exc:  # noqa: BLE001
            logger.warning("[CHAT-PIPE] Llama stream failed — fallback Claude: %s", exc)
        logger.info("[CHAT-PIPE] fallback_provider=claude reason=llama_stream_unavailable")
    elif allow_llama and use_llama() and not should_route_to_llama():
        logger.warning("[CHAT-PIPE] Ollama sin modelo listo — stream fallback Claude")
        logger.info("[CHAT-PIPE] fallback_provider=claude reason=llama_not_ready")

    settings = get_settings()
    anthropic_key = settings.anthropic_api_key.strip()
    if anthropic_key:
        logger.info("[CHAT-PIPE] streaming_with=claude_fallback")
        from app.services.claude_advanced import _iter_anthropic_text_stream

        for piece, label in _iter_anthropic_text_stream(
            api_key=anthropic_key,
            system=system,
            messages=messages,
            max_tokens=max_tokens,
            user_text=user_text,
        ):
            if piece:
                yield piece, label
        return

    from app.services.text_chat import TextChatError

    if not (api_key or "").strip():
        raise TextChatError(
            "Sin ANTHROPIC_API_KEY para fallback cuando Llama no responde.",
            http_status=503,
        )

    from app.services.text_chat import CHAT_GEMINI_MODEL, _gemini_client, _trim_system

    logger.warning("[CHAT-PIPE] Sin Claude — stream fallback Gemini degradado")
    from google.genai import types

    contents: list[types.Content] = []
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        if role == "user":
            contents.append(types.Content(role="user", parts=[types.Part(text=content)]))
        elif role == "assistant":
            contents.append(types.Content(role="model", parts=[types.Part(text=content)]))

    if not contents:
        raise TextChatError("Sin mensajes para el asistente.")

    model_name = (model or CHAT_GEMINI_MODEL).strip() or CHAT_GEMINI_MODEL
    label = model_name
    client = _gemini_client(api_key)
    stream = client.models.generate_content_stream(
        model=model_name,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=_trim_system(system),
            temperature=0.4,
            max_output_tokens=max_tokens,
        ),
    )
    for chunk in stream:
        piece = getattr(chunk, "text", None) or ""
        if piece:
            yield piece, label
