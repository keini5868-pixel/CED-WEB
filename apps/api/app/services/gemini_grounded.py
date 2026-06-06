"""Consultas web para voz — Tavily primero, Gemini Search como respaldo."""

from __future__ import annotations

import datetime
import logging
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Any

from app.config import get_settings
from app.services.tavily_search import tavily_voice_snippet

logger = logging.getLogger(__name__)

BRIEF_MODEL = "gemini-2.5-flash"
# Gemini 2.5 + Google Search consume tokens internos; <512 trunca en MAX_TOKENS.
GEMINI_OUTPUT_TOKENS = 512
TAVILY_TIMEOUT_SEC = 8
GEMINI_TIMEOUT_SEC = 14
MIN_SPOKEN_CHARS = 36


def _is_valid_brief(text: str) -> bool:
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    return len(cleaned) >= MIN_SPOKEN_CHARS


def _generate_brief(client: Any, user_prompt: str) -> str:
    from google.genai import types

    response = client.models.generate_content(
        model=BRIEF_MODEL,
        contents=user_prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            temperature=0.35,
            max_output_tokens=GEMINI_OUTPUT_TOKENS,
        ),
    )
    text = (getattr(response, "text", None) or "").strip()
    if text and _is_valid_brief(text):
        return text

    finish = None
    if response.candidates:
        finish = getattr(response.candidates[0], "finish_reason", None)
    logger.warning(
        "[GEMINI:BRIEF] respuesta corta len=%s finish=%s",
        len(text),
        finish,
    )
    return text


def _spoken_fallback(raw: str) -> str:
    text = re.sub(r"\s+", " ", raw).strip()
    if not text:
        return ""
    if not text.lower().startswith("señor"):
        text = (
            f"Señor, {text[0].lower()}{text[1:]}"
            if len(text) > 1
            else f"Señor, {text}"
        )
    return text[:420]


def _tavily_brief(topic: str, kind: str) -> str:
    return _spoken_fallback(tavily_voice_snippet(topic, kind=kind))


def _gemini_prompt(topic: str, kind: str) -> str:
    today = datetime.date.today().isoformat()
    if kind == "weather":
        return (
            f"Fecha: {today}. Pregunta: {topic}\n\n"
            "Busca el clima ACTUAL en internet. Responde en 2 oraciones cortas "
            "en español latinoamericano para narración por VOZ. "
            "Empieza con 'Señor,'. Sin markdown, URLs ni listas."
        )
    if kind == "news":
        return (
            f"Fecha: {today}. Pregunta: {topic}\n\n"
            "Busca noticias de HOY en internet. Responde en 2 oraciones cortas "
            "en español latinoamericano para narración por VOZ. "
            "Empieza con 'Señor,'. Sin markdown, URLs ni listas."
        )
    return (
        f"Pregunta: {topic}\n\n"
        "Busca en internet y responde en 2-3 oraciones cortas en español "
        "latinoamericano para narración por VOZ. Empieza con 'Señor,'. "
        "Sin markdown, URLs ni listas."
    )


def _run_tavily(topic: str, kind: str) -> str:
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_tavily_brief, topic, kind)
        return future.result(timeout=TAVILY_TIMEOUT_SEC)


def _run_gemini(topic: str, kind: str, api_key: str) -> str:
    from google import genai

    client = genai.Client(api_key=api_key)
    prompt = _gemini_prompt(topic, kind)

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_generate_brief, client, prompt)
        return future.result(timeout=GEMINI_TIMEOUT_SEC)


def fetch_voice_brief(query: str, *, kind: str = "news") -> dict[str, Any]:
    """Resumen hablable: Tavily (~3-5 s) → Gemini Search (~8-12 s)."""
    settings = get_settings()
    topic = (query or "").strip() or "noticias importantes de hoy"
    kind = kind if kind in ("news", "weather", "general") else "general"
    has_tavily = bool(settings.tavily_api_key.strip())
    has_google = bool(settings.google_api_key.strip())

    if not has_tavily and not has_google:
        return {
            "ok": False,
            "error": "Sin TAVILY_API_KEY ni GOOGLE_API_KEY en apps/api/.env",
            "code": "missing_keys",
        }

    if has_tavily:
        try:
            tavily_text = _run_tavily(topic, kind)
            if _is_valid_brief(tavily_text):
                logger.info(
                    "[VOICE:BRIEF] tavily ok kind=%s len=%s", kind, len(tavily_text)
                )
                return {
                    "ok": True,
                    "summary": tavily_text,
                    "kind": kind,
                    "source": "tavily",
                }
            logger.warning("[VOICE:BRIEF] tavily vacío o corto kind=%s", kind)
        except FuturesTimeout:
            logger.warning("[VOICE:BRIEF] tavily timeout kind=%s", kind)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[VOICE:BRIEF] tavily error %s", exc)

    if has_google:
        try:
            gemini_text = _run_gemini(topic, kind, settings.google_api_key.strip())
            if _is_valid_brief(gemini_text):
                logger.info(
                    "[VOICE:BRIEF] gemini ok kind=%s len=%s", kind, len(gemini_text)
                )
                return {
                    "ok": True,
                    "summary": gemini_text,
                    "kind": kind,
                    "source": "gemini",
                }
            logger.warning(
                "[VOICE:BRIEF] gemini incompleto kind=%s len=%s",
                kind,
                len(gemini_text or ""),
            )
        except FuturesTimeout:
            logger.warning("[VOICE:BRIEF] gemini timeout kind=%s", kind)
        except Exception as exc:  # noqa: BLE001
            logger.error("[GEMINI:BRIEF] %s: %s", type(exc).__name__, exc)

    if not has_tavily:
        return {
            "ok": False,
            "error": (
                "Búsqueda web lenta o incompleta. Agregue TAVILY_API_KEY en "
                "apps/api/.env (tavily.com) para resultados rápidos."
            ),
            "code": "missing_tavily",
        }

    return {
        "ok": False,
        "error": "No se obtuvo información suficiente en el tiempo límite",
        "code": "empty_result",
    }
