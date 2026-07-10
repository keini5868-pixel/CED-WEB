"""Streaming Claude dedicado a Finanzas — independiente de Modo Avanzado."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Iterator

import httpx

from app.services.text_chat import CHAT_MODEL, CHAT_MODEL_FAST, _chat_max_tokens

logger = logging.getLogger(__name__)

FINANCE_STREAM_MODEL = CHAT_MODEL_FAST
FINANCE_DEEP_MODEL = CHAT_MODEL
FINANCE_STREAM_LABEL = "claude-haiku"
FINANCE_DEEP_LABEL = "claude-sonnet-4-6"


def finance_history_for_stream(history: list[dict[str, Any]]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for turn in history[-12:]:
        role = str(turn.get("role") or "").strip().lower()
        content = str(turn.get("content") or "").strip()
        if not content:
            continue
        if role in ("user", "human"):
            messages.append({"role": "user", "content": content})
        elif role in ("assistant", "model", "claude"):
            messages.append({"role": "assistant", "content": content})
    return messages[-10:]


def finance_stream_max_tokens(text: str) -> int:
    length = len(text.strip())
    if length < 50:
        return 280
    if length < 180:
        return 700
    return min(1200, _chat_max_tokens(text))


def _needs_sonnet(text: str) -> bool:
    if len(text.strip()) > 420:
        return True
    return bool(
        re.search(
            r"plan\s+de\s+ahorro|informe\s+financiero|an[aá]lisis\s+detallado",
            text,
            re.I,
        )
    )


def _pick_model(text: str) -> tuple[str, str]:
    if _needs_sonnet(text):
        return FINANCE_DEEP_MODEL, FINANCE_DEEP_LABEL
    return FINANCE_STREAM_MODEL, FINANCE_STREAM_LABEL


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


def iter_finance_anthropic_text_stream(
    *,
    api_key: str,
    system: str,
    messages: list[dict[str, Any]],
    max_tokens: int,
    user_text: str,
) -> Iterator[tuple[str, str]]:
    primary, label = _pick_model(user_text)
    fallback = FINANCE_STREAM_MODEL if primary == FINANCE_DEEP_MODEL else FINANCE_DEEP_MODEL
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
                    else (FINANCE_DEEP_LABEL if model == FINANCE_DEEP_MODEL else FINANCE_STREAM_LABEL)
                )
                yield piece, model_label
            return
        except httpx.HTTPStatusError as exc:
            last_exc = exc
            if exc.response.status_code in (400, 404) and model != fallback:
                continue
            raise
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if model != fallback:
                continue
            raise
    if last_exc:
        raise last_exc
