"""Análisis profundo vía Claude (Haiku/Sonnet) — fallback Gemini si Claude falla."""

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
ANALYSIS_TIMEOUT_SEC = 22
# Presupuesto total de voz (Retell tool timeout ~45s). Sin cascada 22+22+22.
VOICE_ANALYSIS_BUDGET_SEC = 36
VOICE_RESULT_LIMIT = 900
VOICE_SCRIPT_LIMIT = 1800


def _is_script_request(topic: str) -> bool:
    return bool(
        re.search(
            r"\b(guion|gui[oó]n|script|narraci|video|demo|presentaci|grabar|secuencia)\b",
            topic,
            re.I,
        )
    )


def _voice_trim(text: str, *, is_script: bool = False) -> str:
    from app.services.voice_spoken import fit_voice_spoken

    t = re.sub(r"```[\s\S]*?```", " ", text or "")
    t = re.sub(r"^#{1,6}\s*", "", t, flags=re.M)
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)
    t = re.sub(r"\*([^*]+)\*", r"\1", t)
    t = re.sub(r"`([^`]+)`", r"\1", t)
    t = re.sub(r"^\s*[-*•]\s+", "", t, flags=re.M)
    t = re.sub(r"\s+", " ", t).strip()
    if not t:
        return ""
    limit = VOICE_SCRIPT_LIMIT if is_script else VOICE_RESULT_LIMIT
    if len(t) <= limit:
        return t
    return fit_voice_spoken(t, max_chars=limit)


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


def _gemini_analysis(api_key: str, user_prompt: str, *, model: str, max_tokens: int = 320) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=[types.Content(role="user", parts=[types.Part(text=user_prompt)])],
        config=types.GenerateContentConfig(
            system_instruction=(
                "Respondes en español latinoamericano para narración por voz. "
                "Oraciones completas. Sin markdown, URLs ni listas."
            ),
            temperature=0.35,
            max_output_tokens=max_tokens,
        ),
    )
    return (response.text or "").strip()


def _run_analysis(topic: str) -> tuple[str | None, str | None]:
    """Returns (text, error)."""
    import time

    settings = get_settings()
    anthropic_key = settings.anthropic_api_key.strip()
    google_key = settings.google_api_key.strip()
    gemini_model = settings.gemini_voice_model.strip() or "gemini-2.5-flash"
    is_script = _is_script_request(topic)
    deadline = time.monotonic() + VOICE_ANALYSIS_BUDGET_SEC

    if is_script:
        user_prompt = (
            f"Consulta: {topic}\n\n"
            "Responde en español latino para NARRACIÓN POR VOZ con un guion COMPLETO "
            "para video corto del sistema CED (Castillo de la Evolución Digital).\n"
            "CED es la inteligencia central de Castillo Digital, creada por Keini Castillo. "
            "Incluye: conversación IA, voz Jarvis, búsqueda web, memoria, cámara/visión, "
            "publicación en redes, prospección, generación de imágenes, mapas/navegación y sistema avanzado.\n"
            "El guion debe durar unos 20-30 segundos al leerlo en voz alta. "
            "Entre 8 y 12 oraciones fluidas y consecutivas. "
            "Empieza enganchando, explica qué es CED y sus características principales. "
            "Cierra OBLIGATORIAMENTE con una oración completa que diga "
            "'Creado por Keini Castillo' o equivalente. "
            "Sin markdown, URLs ni listas con viñetas."
        )
        max_tokens = 1400
    else:
        user_prompt = (
            f"Consulta: {topic}\n\n"
            "Responde en español latinoamericano para VOZ. "
            "Entre 4 y 8 oraciones completas, fluídas y concretas. "
            "Si compara ideas o autores, menciona 2-3 puntos de conexión claros. "
            "Sin markdown, URLs ni listas con viñetas. Cierra en una oración completa."
        )
        max_tokens = 700

    def _remaining() -> float:
        return max(0.5, deadline - time.monotonic())

    def _try_anthropic(model: str) -> str:
        return _anthropic_analysis(anthropic_key, user_prompt, model=model, max_tokens=max_tokens)

    with ThreadPoolExecutor(max_workers=1) as pool:
        if anthropic_key:
            for model, label in (
                (ANALYSIS_MODEL_FAST, "haiku"),
                (ANALYSIS_MODEL_FALLBACK, "sonnet"),
            ):
                remaining = _remaining()
                if remaining < 3:
                    break
                attempt_timeout = min(ANALYSIS_TIMEOUT_SEC, remaining)
                future = pool.submit(_try_anthropic, model)
                try:
                    text = future.result(timeout=attempt_timeout)
                    if text:
                        logger.info(
                            "[CLAUDE:DEEP] provider=anthropic model=%s len=%s leftover=%.1fs",
                            label,
                            len(text),
                            _remaining(),
                        )
                        return _voice_trim(text, is_script=is_script), None
                except FuturesTimeout:
                    logger.warning(
                        "[CLAUDE:DEEP] %s timeout after %.1fs",
                        label,
                        attempt_timeout,
                    )
                except Exception as exc:
                    logger.warning("[CLAUDE:DEEP] %s %s: %s", label, type(exc).__name__, exc)

        if google_key and _remaining() >= 3:
            gemini_tokens = 1400 if is_script else 480
            attempt_timeout = min(ANALYSIS_TIMEOUT_SEC, _remaining())
            future = pool.submit(
                _gemini_analysis,
                google_key,
                user_prompt,
                model=gemini_model,
                max_tokens=gemini_tokens,
            )
            try:
                text = future.result(timeout=attempt_timeout)
                if text:
                    logger.info("[CLAUDE:DEEP] provider=gemini len=%s", len(text))
                    return _voice_trim(text, is_script=is_script), None
            except FuturesTimeout:
                logger.warning("[CLAUDE:DEEP] gemini timeout")
            except Exception as exc:
                logger.warning("[CLAUDE:DEEP] gemini %s: %s", type(exc).__name__, exc)

    if not anthropic_key and not google_key:
        return None, "Ningún proveedor de análisis configurado"
    return None, "El sistema avanzado tardó demasiado"


def consultar_sistema_avanzado(prompt: str) -> dict[str, Any]:
    """Texto hablable para devolver vía function response (voz o chat)."""
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
