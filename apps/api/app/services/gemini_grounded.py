"""Consultas web para voz — Tavily + Gemini Search en paralelo."""

from __future__ import annotations

import asyncio
import datetime
import logging
import re
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Any

from app.config import get_settings
from app.services.tavily_search import tavily_voice_snippet
from app.services.voice_spoken import fit_voice_spoken

logger = logging.getLogger(__name__)

BRIEF_MODEL = "gemini-2.5-flash"
# Gemini 2.5 + Google Search consume tokens internos; <512 trunca en MAX_TOKENS.
GEMINI_OUTPUT_TOKENS = 768
TAVILY_TIMEOUT_SEC = 12
GEMINI_TIMEOUT_SEC = 12
SEARCH_WEB_PARALLEL_TIMEOUT_SEC = 20
SEARCH_WEB_TIMEOUT_SEC = 17.0
MIN_SPOKEN_CHARS = 28
MIN_SPOKEN_CHARS_NEWS = 24
MAX_CONCURRENT_SEARCHES = 3

_search_concurrency = threading.BoundedSemaphore(MAX_CONCURRENT_SEARCHES)


def _is_valid_brief(text: str, *, kind: str = "general") -> bool:
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    min_len = MIN_SPOKEN_CHARS_NEWS if kind == "news" else MIN_SPOKEN_CHARS
    return len(cleaned) >= min_len


def _generate_brief(client: Any, user_prompt: str, *, kind: str = "general") -> str:
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
    if text and _is_valid_brief(text, kind=kind):
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


def _spoken_fallback(raw: str, *, kind: str = "general") -> str:
    text = re.sub(r"\s+", " ", raw).strip()
    if not text:
        return ""
    from app.services.voice_spoken import VOICE_NEWS_MAX_CHARS, fit_voice_spoken

    limit = VOICE_NEWS_MAX_CHARS if kind == "news" else 900
    if len(text) <= limit:
        return text
    return fit_voice_spoken(text, max_chars=limit)


def _gemini_prompt(topic: str, kind: str) -> str:
    today = datetime.date.today().isoformat()
    if kind == "weather":
        return (
            f"Fecha: {today}. Pregunta: {topic}\n\n"
            "Busca el clima ACTUAL en internet. Responde en 2 oraciones cortas "
            "en español latinoamericano para narración por VOZ. "
            "Sin markdown, URLs ni listas."
        )
    if kind == "news":
        return (
            f"Fecha: {today}. Pregunta del usuario: {topic}\n\n"
            "Busca en internet noticias RECIENTES sobre lo que preguntó el usuario. "
            "Responde en 3-4 oraciones COMPLETAS en español latinoamericano para narración por VOZ. "
            "Cierra SIEMPRE la última oración con punto. No dejes frases a medias. "
            "Enfócate en lo pedido (país, persona o tema). "
            "NO repitas introducciones genéricas. Sin markdown, URLs ni listas numeradas."
        )
    return (
        f"Pregunta: {topic}\n\n"
        "Busca en internet y responde en 2-3 oraciones cortas en español "
        "latinoamericano para narración por VOZ. "
        "Sin markdown, URLs ni listas."
    )


def _optimal_search_query(topic: str, kind: str) -> str:
    base = (topic or "").strip()
    if not base:
        return "noticias importantes de hoy"
    if kind == "weather":
        return f"clima tiempo actual hoy {base}"
    if kind == "news":
        return f"noticias de hoy {base}"
    return base


def _run_tavily(topic: str, kind: str) -> str:
    from app.services.tavily_search import infer_tavily_topic

    q = _optimal_search_query(topic, kind)
    tavily_topic = infer_tavily_topic(q, kind=kind)
    logger.info("[SEARCH] tavily topic=%s kind=%s q=%s", tavily_topic, kind, q[:80])
    text = _spoken_fallback(tavily_voice_snippet(q, kind=kind), kind=kind)
    if _is_valid_brief(text, kind=kind):
        return text
    return ""


def _run_gemini(topic: str, kind: str, api_key: str) -> str:
    from google import genai

    client = genai.Client(api_key=api_key)
    q = _optimal_search_query(topic, kind)
    prompt = _gemini_prompt(q, kind)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_generate_brief, client, prompt, kind=kind)
        try:
            last_text = future.result(timeout=GEMINI_TIMEOUT_SEC)
        except FuturesTimeout:
            logger.warning("[VOICE:BRIEF] gemini timeout kind=%s", kind)
            return ""
    if _is_valid_brief(last_text, kind=kind):
        return last_text
    return last_text


async def _run_tavily_async(topic: str, kind: str) -> str:
    return await asyncio.wait_for(
        asyncio.to_thread(_run_tavily, topic, kind),
        timeout=TAVILY_TIMEOUT_SEC,
    )


async def _run_gemini_async(topic: str, kind: str, api_key: str) -> str:
    return await asyncio.wait_for(
        asyncio.to_thread(_run_gemini, topic, kind, api_key),
        timeout=GEMINI_TIMEOUT_SEC,
    )


def _source_from_task_name(name: str) -> str:
    return "tavily" if "tavily" in name else "gemini"


def _log_active_search_tasks() -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    search_tasks = [
        t
        for t in asyncio.all_tasks(loop)
        if t.get_name().startswith(("tavily_", "gemini_"))
    ]
    if search_tasks:
        logger.warning(
            "[SEARCH] %d tasks de búsqueda aún activos: %s",
            len(search_tasks),
            [t.get_name() for t in search_tasks],
        )


async def _cleanup_search_tasks(tasks: list[asyncio.Task[Any]]) -> None:
    for task in tasks:
        if not task.done():
            task.cancel()
    for task in tasks:
        if task.cancelled():
            continue
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass


async def _cancel_pending_tasks(tasks: list[asyncio.Task[Any]]) -> None:
    await _cleanup_search_tasks(tasks)


async def fetch_voice_brief_parallel(query: str, *, kind: str = "news") -> dict[str, Any]:
    """Tavily y Gemini en paralelo — usa el primero con resultado válido."""
    acquired = _search_concurrency.acquire(timeout=SEARCH_WEB_TIMEOUT_SEC + 5)
    if not acquired:
        logger.warning("[SEARCH] cola llena — demasiadas búsquedas simultáneas")
        return {
            "ok": False,
            "error": "Demasiadas búsquedas en curso. Intente de nuevo en unos segundos.",
            "code": "search_busy",
            "status": "timeout",
            "fallback": True,
            "spoken": "Un momento, señor. Estoy procesando otra consulta.",
        }

    settings = get_settings()
    topic = (query or "").strip() or "noticias importantes de hoy"
    kind = kind if kind in ("news", "weather", "general") else "general"
    has_tavily = bool(settings.tavily_api_key.strip())
    has_google = bool(settings.google_api_key.strip())
    api_key = settings.google_api_key.strip()
    query_tag = str(abs(hash(topic)))[-8:]

    if not has_tavily and not has_google:
        _search_concurrency.release()
        return {
            "ok": False,
            "error": "Sin TAVILY_API_KEY ni GOOGLE_API_KEY en apps/api/.env",
            "code": "missing_keys",
        }

    tasks: list[asyncio.Task[str]] = []
    result: dict[str, Any] | None = None
    response_id = str(uuid.uuid4())[:8]

    try:
        if has_tavily:
            tavily_task = asyncio.create_task(_run_tavily_async(topic, kind))
            tavily_task.set_name(f"tavily_{query_tag}")
            tasks.append(tavily_task)
        if has_google:
            gemini_task = asyncio.create_task(_run_gemini_async(topic, kind, api_key))
            gemini_task.set_name(f"gemini_{query_tag}")
            tasks.append(gemini_task)

        pending = set(tasks)
        deadline = asyncio.get_running_loop().time() + SEARCH_WEB_PARALLEL_TIMEOUT_SEC
        while pending and result is None:
            timeout = max(0.1, deadline - asyncio.get_running_loop().time())
            done, pending = await asyncio.wait(
                pending,
                timeout=timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if not done:
                logger.warning("[SEARCH] timeout total kind=%s id=%s", kind, response_id)
                break

            for task in done:
                name = task.get_name()
                try:
                    candidate = task.result()
                    if candidate and _is_valid_brief(candidate, kind=kind):
                        result = {
                            "ok": True,
                            "summary": candidate,
                            "kind": kind,
                            "source": _source_from_task_name(name),
                            "response_id": response_id,
                        }
                        logger.info("[SEARCH] resultado de %s id=%s", name, response_id)
                        break
                except Exception as exc:  # noqa: BLE001
                    logger.warning("[SEARCH] task falló %s: %s", name, exc)

        for task in list(pending):
            if not task.done():
                task.cancel()
        for task in list(pending):
            if task.cancelled():
                continue
            try:
                late = task.result()
                if late and _is_valid_brief(str(late), kind=kind):
                    logger.warning(
                        "[SEARCH] respuesta duplicada descartada (id=%s task=%s)",
                        response_id,
                        task.get_name(),
                    )
            except (asyncio.CancelledError, Exception):
                pass

        if result:
            return result

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
            "status": "timeout",
            "fallback": True,
            "spoken": "Sin resultados disponibles.",
        }
    except Exception as exc:  # noqa: BLE001
        logger.error("[SEARCH] error paralelismo: %s", exc)
        return {
            "ok": False,
            "error": str(exc),
            "code": "error",
            "status": "error",
            "fallback": True,
            "spoken": "Sin resultados disponibles.",
        }
    finally:
        await _cleanup_search_tasks(tasks)
        _log_active_search_tasks()
        _search_concurrency.release()


def fetch_voice_brief(query: str, *, kind: str = "news") -> dict[str, Any]:
    """Wrapper síncrono para callers legacy (thread pool / rutas sync)."""
    return asyncio.run(fetch_voice_brief_parallel(query, kind=kind))


async def execute_search_web(query: str, *, kind: str = "general") -> dict[str, Any]:
    """Paralelismo Tavily+Gemini con timeout unificado (voz y chat)."""
    q = (query or "").strip()
    if not q:
        return {
            "ok": False,
            "status": "error",
            "fallback": True,
            "message": "Consulta de búsqueda vacía.",
            "summary": "",
        }
    try:
        result = await asyncio.wait_for(
            fetch_voice_brief_parallel(q, kind=kind),
            timeout=SEARCH_WEB_TIMEOUT_SEC,
        )
    except asyncio.TimeoutError:
        logger.warning("[WEB_SEARCH] timeout query=%s kind=%s", q[:80], kind)
        return {
            "ok": False,
            "status": "timeout",
            "fallback": True,
            "message": (
                "Señor, no pude obtener información actual en este momento. "
                "Según lo que tengo registrado, puedo orientarle con conocimiento general."
            ),
            "summary": "",
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("[WEB_SEARCH] error query=%s: %s", q[:80], exc)
        return {
            "ok": False,
            "status": "error",
            "fallback": True,
            "message": (
                "Señor, no pude obtener información actual en este momento. "
                "Según lo que tengo registrado, puedo orientarle con conocimiento general."
            ),
            "summary": "",
        }

    summary = str(result.get("summary") or "").strip()
    if result.get("ok") and summary:
        return {
            "ok": True,
            "status": "success",
            "fallback": False,
            "message": summary,
            "summary": summary,
            "source": result.get("source"),
            "kind": kind,
        }
    logger.warning(
        "[WEB_SEARCH] empty/fail kind=%s code=%s",
        kind,
        result.get("code"),
    )
    return {
        "ok": False,
        "status": "timeout",
        "fallback": True,
        "message": str(
            result.get("spoken")
            or result.get("error")
            or "Señor, no pude obtener información actual en este momento."
        ),
        "summary": "",
    }


def execute_search_web_sync(query: str, *, kind: str = "general") -> dict[str, Any]:
    """Wrapper síncrono para chat de texto y router cognitivo."""
    coro = execute_search_web(query, kind=kind)
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(asyncio.run, coro)
        return future.result(timeout=SEARCH_WEB_TIMEOUT_SEC + 10)
