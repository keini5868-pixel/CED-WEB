"""Análisis profundo vía Claude — herramienta `consultar_claude` en voz Realtime."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

ANALYSIS_MODEL = "claude-sonnet-4-6"
ANALYSIS_TIMEOUT_SEC = 26


def _anthropic_analysis(api_key: str, user_prompt: str) -> str:
    with httpx.Client(timeout=ANALYSIS_TIMEOUT_SEC + 4) as client:
        res = client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": ANALYSIS_MODEL,
                "max_tokens": 480,
                "temperature": 0.45,
                "messages": [{"role": "user", "content": user_prompt}],
            },
        )
        res.raise_for_status()
        data = res.json()
    blocks = data.get("content") or []
    parts = [b.get("text", "") for b in blocks if b.get("type") == "text"]
    return "".join(parts).strip()


def consultar_sistema_avanzado(prompt: str) -> dict[str, Any]:
    """Texto hablable para devolver a OpenAI Realtime vía function response."""
    settings = get_settings()
    api_key = settings.anthropic_api_key.strip()
    topic = (prompt or "").strip()
    if not topic:
        return {"ok": False, "error": "Consulta vacía"}

    if not api_key:
        return {"ok": False, "error": "ANTHROPIC_API_KEY no configurada"}

    user_prompt = (
        f"Consulta del usuario: {topic}\n\n"
        "Responde en español latinoamericano para NARRACIÓN POR VOZ. "
        "Máximo 4 oraciones claras. Sin markdown, URLs ni listas con guiones. "
        "Sé preciso y directo."
    )

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_anthropic_analysis, api_key, user_prompt)
            try:
                text = future.result(timeout=ANALYSIS_TIMEOUT_SEC)
            except FuturesTimeout:
                logger.warning("[CLAUDE:DEEP] timeout")
                return {"ok": False, "error": "El sistema avanzado tardó demasiado"}

        if not text:
            return {"ok": False, "error": "Sin respuesta del sistema avanzado"}

        logger.info("[CLAUDE:DEEP] ok len=%s", len(text))
        return {"ok": True, "result": text}
    except Exception as exc:
        logger.error("[CLAUDE:DEEP] %s: %s", type(exc).__name__, exc)
        return {"ok": False, "error": str(exc)}
