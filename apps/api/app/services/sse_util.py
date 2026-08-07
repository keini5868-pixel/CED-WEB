"""Shared SSE helpers — coerce text fields so clients never stringify objects."""

from __future__ import annotations

import json
from typing import Any

_TEXT_KEYS = frozenset(
    {
        "text",
        "reply",
        "response",
        "status",
        "message",
        "model",
        "conversation_id",
    }
)


def _coerce_sse_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                t = item.get("text") or item.get("content") or ""
                if t:
                    parts.append(str(t))
            else:
                parts.append(str(item))
        return "\n".join(p for p in parts if p)
    if isinstance(value, dict):
        nested = (
            value.get("text")
            or value.get("content")
            or value.get("reply")
            or value.get("response")
        )
        if nested is not None:
            return str(nested)
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def sse_event(name: str, payload: dict[str, Any]) -> str:
    safe: dict[str, Any] = {}
    for key, value in payload.items():
        if key in _TEXT_KEYS:
            safe[key] = _coerce_sse_text(value)
        else:
            safe[key] = value
    return f"event: {name}\ndata: {json.dumps(safe, ensure_ascii=False)}\n\n"


def sse_flush() -> str:
    """Comentario SSE para forzar flush en proxies (Railway / Next.js)."""
    return ": flush\n\n"
