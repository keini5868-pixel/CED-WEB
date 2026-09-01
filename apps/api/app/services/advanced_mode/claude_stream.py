"""Streaming y respuestas Claude — exclusivo Modo Avanzado."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Iterator

import httpx

from app.config import get_settings
from app.services.advanced_mode.constants import (
    ADVANCED_DEEP_MODEL,
    ADVANCED_DEEP_MODEL_LABEL,
    ADVANCED_STREAM_MODEL,
    ADVANCED_STREAM_MODEL_LABEL,
)
from app.services.text_chat import CHAT_DELIVERABLE_MAX_TOKENS, _chat_max_tokens

logger = logging.getLogger(__name__)


def require_anthropic_api_key() -> str:
    key = get_settings().anthropic_api_key.strip()
    if not key:
        raise ValueError("missing_anthropic_api_key")
    return key


def advanced_is_configured() -> bool:
    return bool(get_settings().anthropic_api_key.strip())


def _needs_sonnet_stream(text: str) -> bool:
    if len(text.strip()) > 420:
        return True
    return bool(
        re.search(
            r"estrategia\s+completa|plan\s+de\s+negocio|an[aá]lisis\s+profundo|"
            r"informe\s+detallado|roadmap|plan\s+maestro|plan\s+ejecutivo",
            text,
            re.I,
        )
    )


def _pick_stream_model(text: str) -> tuple[str, str]:
    if _needs_sonnet_stream(text):
        return ADVANCED_DEEP_MODEL, ADVANCED_DEEP_MODEL_LABEL
    return ADVANCED_STREAM_MODEL, ADVANCED_STREAM_MODEL_LABEL


def stream_max_tokens(
    text: str,
    *,
    history: list | None = None,
) -> int:
    from app.services.deliverable_replies import needs_deliverable_token_budget
    from app.services.text_chat import CHAT_DELIVERABLE_MAX_TOKENS

    if needs_deliverable_token_budget(text, history):
        return CHAT_DELIVERABLE_MAX_TOKENS
    length = len(text.strip())
    if length < 50:
        return 280
    if length < 180:
        return 700
    if _needs_sonnet_stream(text):
        return _chat_max_tokens(text)
    return min(1200, _chat_max_tokens(text))


def _stream_model_text(
    *,
    api_key: str,
    system: str,
    messages: list[dict[str, Any]],
    max_tokens: int,
    model: str,
) -> Iterator[str]:
    timeout = httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=10.0)
    with httpx.Client(timeout=timeout) as client:
        with client.stream(
            "POST",
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": max_tokens,
                "temperature": 0.25,
                "system": system,
                "messages": messages,
                "stream": True,
            },
        ) as res:
            res.raise_for_status()
            for raw_line in res.iter_lines():
                if not raw_line or not raw_line.startswith("data: "):
                    continue
                chunk = raw_line[6:].strip()
                if chunk == "[DONE]":
                    break
                try:
                    data = json.loads(chunk)
                except json.JSONDecodeError:
                    continue
                if data.get("type") == "content_block_delta":
                    delta = data.get("delta") or {}
                    if delta.get("type") == "text_delta":
                        piece = str(delta.get("text") or "")
                        if piece:
                            yield piece


def iter_advanced_claude_stream(
    *,
    api_key: str,
    system: str,
    messages: list[dict[str, Any]],
    max_tokens: int,
    user_text: str,
) -> Iterator[tuple[str, str]]:
    """Yield (text_chunk, model_label)."""
    primary, label = _pick_stream_model(user_text)
    fallback = (
        ADVANCED_STREAM_MODEL if primary == ADVANCED_DEEP_MODEL else ADVANCED_DEEP_MODEL
    )
    last_exc: Exception | None = None
    for model in (primary, fallback):
        try:
            for piece in _stream_model_text(
                api_key=api_key,
                system=system,
                messages=messages,
                max_tokens=max_tokens,
                model=model,
            ):
                model_label = (
                    label
                    if model == primary
                    else (
                        ADVANCED_DEEP_MODEL_LABEL
                        if model == ADVANCED_DEEP_MODEL
                        else ADVANCED_STREAM_MODEL_LABEL
                    )
                )
                yield piece, model_label
            return
        except httpx.HTTPStatusError as exc:
            last_exc = exc
            if exc.response.status_code in (400, 404) and model != fallback:
                logger.warning("[ADV-MODE] stream model %s unavailable, fallback", model)
                continue
            raise
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if model != fallback:
                continue
            raise
    if last_exc:
        raise last_exc


def anthropic_simple_reply(
    *,
    api_key: str,
    system: str,
    messages: list[dict[str, Any]],
    max_tokens: int,
    user_text: str = "",
) -> str | None:
    primary, _ = _pick_stream_model(user_text)
    payload = {
        "model": primary,
        "max_tokens": min(max_tokens, CHAT_DELIVERABLE_MAX_TOKENS),
        "temperature": 0.25,
        "system": system,
        "messages": messages,
    }
    try:
        with httpx.Client(timeout=60.0) as client:
            res = client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json=payload,
            )
            res.raise_for_status()
            data = res.json()
        blocks = data.get("content") or []
        return "".join(
            b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text"
        ).strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[ADV-MODE] simple reply failed: %s", exc)
        return None
