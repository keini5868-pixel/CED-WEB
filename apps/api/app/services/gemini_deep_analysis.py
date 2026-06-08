"""Análisis profundo para herramienta Live `consultar_sistema_avanzado`."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)

ANALYSIS_MODEL = "gemini-2.5-flash"
ANALYSIS_TIMEOUT_SEC = 26


def _generate_analysis(client: Any, user_prompt: str) -> str:
    response = client.models.generate_content(
        model=ANALYSIS_MODEL,
        contents=user_prompt,
        config={
            "temperature": 0.45,
            "max_output_tokens": 480,
        },
    )
    return (getattr(response, "text", None) or "").strip()


def consultar_sistema_avanzado(prompt: str) -> dict[str, Any]:
    """Texto hablable para devolver a Gemini Live vía function response."""
    settings = get_settings()
    api_key = settings.google_api_key.strip()
    topic = (prompt or "").strip()
    if not topic:
        return {"ok": False, "error": "Consulta vacía"}

    if not api_key:
        return {"ok": False, "error": "GOOGLE_API_KEY no configurada"}

    user_prompt = (
        f"Consulta del usuario: {topic}\n\n"
        "Responde en español latinoamericano para NARRACIÓN POR VOZ. "
        "Máximo 4 oraciones claras. Sin markdown, URLs ni listas con guiones. "
        "Sé preciso y directo. Español latinoamericano natural."
    )

    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_generate_analysis, client, user_prompt)
            try:
                text = future.result(timeout=ANALYSIS_TIMEOUT_SEC)
            except FuturesTimeout:
                logger.warning("[GEMINI:DEEP] timeout")
                return {
                    "ok": False,
                    "error": "El sistema avanzado tardó demasiado",
                }

        if not text:
            return {"ok": False, "error": "Sin respuesta del sistema avanzado"}

        logger.info("[GEMINI:DEEP] ok len=%s", len(text))
        return {"ok": True, "result": text}
    except Exception as exc:
        logger.error("[GEMINI:DEEP] %s: %s", type(exc).__name__, exc)
        return {"ok": False, "error": str(exc)}
