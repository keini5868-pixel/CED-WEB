"""Chat avanzado CED — motor Claude Opus (análisis profundo)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

ADVANCED_MODEL = "claude-opus-4-6"
ADVANCED_MODEL_FALLBACK = "claude-sonnet-4-6"

ADVANCED_SYSTEM_PROMPT = """Eres el sistema avanzado de CED — Castillo Evolución Digital. Eres un analista \
experto en negocios, marketing digital, ventas, estrategia empresarial y tecnología.

Tu propósito es dar análisis profundos, detallados y accionables. No das respuestas superficiales — das \
estrategias completas, análisis exhaustivos y soluciones reales.

Responde siempre en español, de forma profesional pero cercana. Dirígete al usuario como "señor" o por \
su nombre si lo conoces."""


def _normalize_history(history: list[dict[str, Any]]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for turn in history[-10:]:
        role = str(turn.get("role") or "").strip().lower()
        content = str(turn.get("content") or "").strip()
        if not content:
            continue
        if role in ("user", "human"):
            messages.append({"role": "user", "content": content})
        elif role in ("assistant", "model", "claude"):
            messages.append({"role": "assistant", "content": content})
    return messages


def _anthropic_chat(
    *,
    api_key: str,
    message: str,
    history: list[dict[str, str]],
    model: str,
) -> str:
    messages = [*history, {"role": "user", "content": message}]
    with httpx.Client(timeout=120.0) as client:
        res = client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": 4096,
                "temperature": 0.4,
                "system": ADVANCED_SYSTEM_PROMPT,
                "messages": messages,
            },
        )
        res.raise_for_status()
        data = res.json()
    blocks = data.get("content") or []
    parts = [b.get("text", "") for b in blocks if b.get("type") == "text"]
    text = "".join(parts).strip()
    if not text:
        raise RuntimeError("Claude devolvió respuesta vacía.")
    return text


async def claude_advanced_chat(
    message: str,
    history: list[dict[str, Any]],
    user_id: str,
) -> tuple[str, str]:
    """Análisis avanzado con Claude — retorna (texto, modelo usado)."""
    _ = user_id  # reservado para personalización futura
    settings = get_settings()
    api_key = settings.anthropic_api_key.strip()
    if not api_key:
        raise ValueError("missing_anthropic_api_key")

    normalized = _normalize_history(history)
    last_exc: Exception | None = None
    for model in (ADVANCED_MODEL, ADVANCED_MODEL_FALLBACK):
        try:
            text = _anthropic_chat(
                api_key=api_key,
                message=message.strip(),
                history=normalized,
                model=model,
            )
            return text, model
        except httpx.HTTPStatusError as exc:
            last_exc = exc
            if exc.response.status_code in (404, 400) and model != ADVANCED_MODEL_FALLBACK:
                logger.warning("[ADVANCED] model %s unavailable, fallback", model)
                continue
            raise
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if model != ADVANCED_MODEL_FALLBACK:
                continue
            raise
    if last_exc:
        raise last_exc
    raise RuntimeError("Claude no respondió.")
