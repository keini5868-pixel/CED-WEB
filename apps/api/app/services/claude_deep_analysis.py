"""Análisis profundo vía Claude (Haiku) u OpenAI — herramienta `consultar_claude` en voz Realtime."""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

ANALYSIS_MODEL_FAST = "claude-haiku-4-5-20251001"
ANALYSIS_MODEL_FALLBACK = "claude-sonnet-4-6"
OPENAI_ANALYSIS_MODEL = "gpt-4o-mini"
ANALYSIS_TIMEOUT_SEC = 16
VOICE_RESULT_LIMIT = 480


def _voice_trim(text: str) -> str:
    t = re.sub(r"\s+", " ", text).strip()
    return t[:VOICE_RESULT_LIMIT] if t else ""


def _anthropic_analysis(api_key: str, user_prompt: str, *, model: str, max_tokens: int) -> str:
    with httpx.Client(timeout=ANALYSIS_TIMEOUT_SEC + 3) as client:
        res = client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": max_tokens,
                "temperature": 0.35,
                "messages": [{"role": "user", "content": user_prompt}],
            },
        )
        res.raise_for_status()
        data = res.json()
    blocks = data.get("content") or []
    parts = [b.get("text", "") for b in blocks if b.get("type") == "text"]
    return "".join(parts).strip()


def _openai_analysis(api_key: str, user_prompt: str) -> str:
    with httpx.Client(timeout=ANALYSIS_TIMEOUT_SEC + 2) as client:
        res = client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": OPENAI_ANALYSIS_MODEL,
                "max_tokens": 220,
                "temperature": 0.35,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Respondes en español latinoamericano para narración por voz. "
                            "Máximo 3 oraciones cortas. Sin markdown, URLs ni listas."
                        ),
                    },
                    {"role": "user", "content": user_prompt},
                ],
            },
        )
        res.raise_for_status()
        data = res.json()
    choices = data.get("choices") or []
    if not choices:
        return ""
    return str(choices[0].get("message", {}).get("content", "")).strip()


def _run_analysis(topic: str) -> tuple[str | None, str | None]:
    """Returns (text, error)."""
    settings = get_settings()
    anthropic_key = settings.anthropic_api_key.strip()
    openai_key = settings.openai_api_key.strip()

    user_prompt = (
        f"Consulta: {topic}\n\n"
        "Responde en español latino para VOZ. Máximo 2-3 oraciones cortas. "
        "Preciso, directo. Sin markdown ni URLs."
    )

    def _try_anthropic(model: str) -> str:
        return _anthropic_analysis(anthropic_key, user_prompt, model=model, max_tokens=220)

    with ThreadPoolExecutor(max_workers=1) as pool:
        if anthropic_key:
            future = pool.submit(_try_anthropic, ANALYSIS_MODEL_FAST)
            try:
                text = future.result(timeout=ANALYSIS_TIMEOUT_SEC)
                if text:
                    return _voice_trim(text), None
            except FuturesTimeout:
                logger.warning("[CLAUDE:DEEP] haiku timeout")
            except Exception as exc:
                logger.warning("[CLAUDE:DEEP] haiku %s: %s", type(exc).__name__, exc)

            future = pool.submit(_try_anthropic, ANALYSIS_MODEL_FALLBACK)
            try:
                text = future.result(timeout=ANALYSIS_TIMEOUT_SEC)
                if text:
                    return _voice_trim(text), None
            except FuturesTimeout:
                logger.warning("[CLAUDE:DEEP] sonnet timeout")
            except Exception as exc:
                logger.warning("[CLAUDE:DEEP] sonnet %s: %s", type(exc).__name__, exc)

        if openai_key:
            future = pool.submit(_openai_analysis, openai_key, user_prompt)
            try:
                text = future.result(timeout=ANALYSIS_TIMEOUT_SEC)
                if text:
                    return _voice_trim(text), None
            except FuturesTimeout:
                logger.warning("[CLAUDE:DEEP] openai timeout")
            except Exception as exc:
                logger.warning("[CLAUDE:DEEP] openai %s: %s", type(exc).__name__, exc)

    if not anthropic_key and not openai_key:
        return None, "Ningún proveedor de análisis configurado"
    return None, "El sistema avanzado tardó demasiado"


def consultar_sistema_avanzado(prompt: str) -> dict[str, Any]:
    """Texto hablable para devolver a OpenAI Realtime vía function response."""
    topic = (prompt or "").strip()
    if not topic:
        return {"ok": False, "error": "Consulta vacía"}

    try:
        text, err = _run_analysis(topic)
        if text:
            logger.info("[CLAUDE:DEEP] ok len=%s", len(text))
            return {"ok": True, "result": text}
        return {"ok": False, "error": err or "Sin respuesta del sistema avanzado"}
    except Exception as exc:
        logger.error("[CLAUDE:DEEP] %s: %s", type(exc).__name__, exc)
        return {"ok": False, "error": str(exc)}
