"""Cerebro conversacional local vía Ollama (Llama).

Reemplaza Gemini para generación de texto en todos los canales excepto Chat Avanzado
(Claude). Sin function-calling autónomo: el orquestador determinista ejecuta módulos.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

# System prompt base para Llama — obediente, sin tools autónomas.
LLAMA_CONVERSATIONAL_SYSTEM = """Eres un asistente conversacional inteligente en español.
Detecta intención del usuario automáticamente (publicar, guardar, enviar, etc.).
ANTES de ejecutar: pide confirmación explícita.
NUNCA llames tools por tu cuenta. NUNCA tomes decisiones sin confirmación.
Siempre responde conversacionalmente, con empatía, en contexto modular."""

_DEFAULT_TIMEOUT_SEC = 120.0
# Texto (13B) en CPU en Railway: medido en producción, agota este timeout
# prácticamente siempre (no produce ni el primer token) — el usuario terminaba
# esperando el timeout COMPLETO antes de que el pipeline recién empezara con
# Claude. Se acorta a un presupuesto "fail-fast": si Llama no arranca en este
# tiempo, se cae a Claude de inmediato en vez de sumar ~18s de espera muerta
# a cada turno de chat. Si Llama sí llega a responder rápido, no se ve afectado.
_CHAT_TIMEOUT_SEC = 5.0
# Voz (3B): objetivo sub-5 s; margen para no cortar antes del HTTP.
_VOICE_CHAT_TIMEOUT_SEC = 14.0
_HEALTH_TIMEOUT_SEC = 3.0
_MODEL_READY_CACHE_TTL_SEC = 15.0
_CHAT_HEALTH_TIMEOUT_SEC = 2.0
_OLLAMA_KEEP_ALIVE = "24h"

# Cacheado por (base, modelo): antes de generar, tanto should_route_to_llama
# (fast_probe) como call_llama_chat/iter_llama_chat_stream comprobaban el
# mismo /api/tags por separado — dos round-trips síncronos antes de cada
# turno de chat. Con esta cache, el segundo check reusa el resultado reciente
# en vez de golpear la red otra vez.
_model_ready_cache: dict[tuple[str, str], tuple[float, bool]] = {}


class LlamaNotReadyError(RuntimeError):
    """Ollama responde pero el modelo configurado no está descargado."""


def _normalize_ollama_endpoint(raw: str) -> str:
    endpoint = (raw or "").strip()
    if not endpoint:
        return "http://localhost:11434"
    for suffix in ("/api/generate", "/api/chat", "/api/tags"):
        if endpoint.endswith(suffix):
            return endpoint[: -len(suffix)]
    return endpoint.rstrip("/")


def _ollama_base() -> str:
    return _normalize_ollama_endpoint(get_settings().llama_endpoint)


def _ollama_voice_base() -> str:
    voice = (get_settings().llama_voice_endpoint or "").strip()
    if voice:
        return _normalize_ollama_endpoint(voice)
    return _ollama_base()


def llama_voice_endpoint_separate() -> bool:
    """True si voz usa un Ollama distinto al de texto."""
    return bool((get_settings().llama_voice_endpoint or "").strip())


def _chat_url(*, base: str | None = None) -> str:
    return f"{(base or _ollama_base())}/api/chat"


def _generate_url(*, base: str | None = None) -> str:
    return f"{(base or _ollama_base())}/api/generate"


def _tags_url(*, base: str | None = None) -> str:
    return f"{(base or _ollama_base())}/api/tags"


def _voice_chat_url() -> str:
    return _chat_url(base=_ollama_voice_base())


def _voice_generate_url() -> str:
    return _generate_url(base=_ollama_voice_base())


def _voice_tags_url() -> str:
    return _tags_url(base=_ollama_voice_base())


def llama_model() -> str:
    return (get_settings().llama_model or "llama3.1:8b").strip() or "llama3.1:8b"


def llama_voice_model() -> str:
    """Modelo liviano para conversación de voz en tiempo real."""
    voice = (get_settings().llama_voice_model or "llama3.2:3b").strip()
    return voice or "llama3.2:3b"


def use_llama() -> bool:
    """True si el proveedor conversacional configurado es Llama local."""
    provider = (get_settings().llm_provider or "").strip().lower()
    if provider == "llama":
        return True
    if provider == "gemini":
        return False
    # retell_llm_provider como alias para voz si llm_provider no está explícito
    return (get_settings().retell_llm_provider or "").strip().lower() == "llama"


def llama_health_diagnostics() -> dict[str, Any]:
    """Diagnóstico Ollama texto (13B) — endpoint LLAMA_ENDPOINT."""
    base = _ollama_base()
    url = _tags_url(base=base)
    result: dict[str, Any] = {
        "role": "text",
        "url": url,
        "endpoint": base,
        "model": llama_model(),
        "timeout_sec": _HEALTH_TIMEOUT_SEC,
        "ok": False,
    }
    try:
        started = time.monotonic()
        with httpx.Client(timeout=_HEALTH_TIMEOUT_SEC) as client:
            response = client.get(url)
        result["latency_ms"] = int((time.monotonic() - started) * 1000)
        result["status_code"] = response.status_code
        if response.status_code == 200:
            data = response.json()
            models = data.get("models") or []
            names = [
                str(m.get("name") or "")
                for m in models
                if isinstance(m, dict) and m.get("name")
            ]
            result["models"] = names
            target = llama_model()
            result["model_ready"] = target in names or any(
                target.split(":")[0] in n for n in names
            )
            result["daemon_ok"] = True
            result["ok"] = bool(result["model_ready"])
        else:
            result["daemon_ok"] = False
            result["error"] = f"HTTP {response.status_code}"
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"{type(exc).__name__}: {exc}"
        logger.warning("[LLAMA] text health check failed url=%s err=%s", url, exc)
    return result


def llama_voice_health_diagnostics() -> dict[str, Any]:
    """Diagnóstico Ollama voz (3B) — LLAMA_VOICE_ENDPOINT o fallback."""
    base = _ollama_voice_base()
    url = _tags_url(base=base)
    result: dict[str, Any] = {
        "role": "voice",
        "url": url,
        "endpoint": base,
        "voice_model": llama_voice_model(),
        "separate_endpoint": llama_voice_endpoint_separate(),
        "timeout_sec": _HEALTH_TIMEOUT_SEC,
        "ok": False,
    }
    try:
        started = time.monotonic()
        with httpx.Client(timeout=_HEALTH_TIMEOUT_SEC) as client:
            response = client.get(url)
        result["latency_ms"] = int((time.monotonic() - started) * 1000)
        result["status_code"] = response.status_code
        if response.status_code == 200:
            data = response.json()
            models = data.get("models") or []
            names = [
                str(m.get("name") or "")
                for m in models
                if isinstance(m, dict) and m.get("name")
            ]
            result["models"] = names
            voice_target = llama_voice_model()
            result["voice_model_ready"] = voice_target in names or any(
                voice_target.split(":")[0] in n for n in names
            )
            result["daemon_ok"] = True
            result["ok"] = bool(result["voice_model_ready"])
        else:
            result["daemon_ok"] = False
            result["error"] = f"HTTP {response.status_code}"
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"{type(exc).__name__}: {exc}"
        logger.warning("[LLAMA] voice health check failed url=%s err=%s", url, exc)
    return result


def llama_combined_health_diagnostics() -> dict[str, Any]:
    """Diagnóstico unificado — texto y voz por separado."""
    text = llama_health_diagnostics()
    voice = llama_voice_health_diagnostics()
    return {
        "text": text,
        "voice": voice,
        "voice_endpoint_separate": llama_voice_endpoint_separate(),
        "ok": bool(text.get("ok")) and bool(voice.get("ok")),
    }


def _llama_health_model_ready(
    *,
    timeout_sec: float,
    model_name: str | None = None,
    base: str | None = None,
) -> bool:
    url = _tags_url(base=base or _ollama_base())
    target = (model_name or llama_model()).strip()
    try:
        with httpx.Client(timeout=timeout_sec) as client:
            response = client.get(url)
        if response.status_code != 200:
            return False
        data = response.json()
        models = data.get("models") or []
        names = [
            str(m.get("name") or "")
            for m in models
            if isinstance(m, dict) and m.get("name")
        ]
        return target in names or any(target.split(":")[0] in n for n in names)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[LLAMA] health check failed url=%s err=%s", url, exc)
        return False


def _cached_model_ready(
    *,
    model_name: str,
    base: str,
    timeout_sec: float,
    force_refresh: bool = False,
) -> bool:
    global _model_ready_cache
    key = (base, model_name)
    now = time.monotonic()
    if not force_refresh:
        cached = _model_ready_cache.get(key)
        if cached is not None and now - cached[0] < _MODEL_READY_CACHE_TTL_SEC:
            return cached[1]
    ready = bool(_llama_health_model_ready(timeout_sec=timeout_sec, model_name=model_name, base=base))
    _model_ready_cache[key] = (now, ready)
    return ready


def llama_model_ready(*, force_refresh: bool = False, timeout_sec: float | None = None) -> bool:
    """True si Ollama tiene el modelo configurado (no solo el daemon)."""
    probe_timeout = timeout_sec if timeout_sec is not None else _HEALTH_TIMEOUT_SEC
    return _cached_model_ready(
        model_name=llama_model(),
        base=_ollama_base(),
        timeout_sec=probe_timeout,
        force_refresh=force_refresh,
    )


def llama_voice_model_ready(*, timeout_sec: float | None = None) -> bool:
    """True si el modelo liviano de voz está descargado en su Ollama."""
    probe_timeout = timeout_sec if timeout_sec is not None else _HEALTH_TIMEOUT_SEC
    return _cached_model_ready(
        model_name=llama_voice_model(),
        base=_ollama_voice_base(),
        timeout_sec=probe_timeout,
    )


def should_route_to_llama(*, fast_probe: bool = False) -> bool:
    """Usar Llama solo si está configurado Y el modelo está listo."""
    if not use_llama():
        return False
    if fast_probe:
        return llama_model_ready(timeout_sec=_CHAT_HEALTH_TIMEOUT_SEC)
    return llama_model_ready()


def llama_available() -> bool:
    """Modelo listo para inferencia — no solo daemon Ollama."""
    return llama_model_ready()


def _log_queue_wait(started: float, *, endpoint: str) -> None:
    """Tiempo hasta primer byte de inferencia (cola Ollama + arranque)."""
    ms = int((time.monotonic() - started) * 1000)
    logger.info("[LLAMA] queue_wait_ms=%s endpoint=%s model=%s", ms, endpoint, llama_model())


def _ollama_unload_model(model: str, *, base: str | None = None) -> None:
    """Libera RAM descargando un modelo de Ollama (best-effort, no lanza)."""
    target = (model or "").strip()
    if not target:
        return
    payload = {"model": target, "prompt": "", "keep_alive": 0}
    try:
        with httpx.Client(timeout=2.0) as client:
            client.post(_generate_url(base=base), json=payload)
        logger.info("[LLAMA] unload_model=%s base=%s", target, base or _ollama_base())
    except Exception as exc:  # noqa: BLE001
        logger.debug("[LLAMA] unload_model skipped model=%s err=%s", target, exc)


def _parse_generate_response(data: dict[str, Any]) -> str:
    return str(data.get("response") or "").strip()


def _parse_chat_response(data: dict[str, Any]) -> str:
    msg = data.get("message") or {}
    text = str(msg.get("content") or "").strip()
    if not text:
        text = str(msg.get("thinking") or "").strip()
    return text


def _raise_if_llama_http_error(response: httpx.Response) -> None:
    if response.status_code == 404:
        body = response.text.lower()
        if "not found" in body or "model" in body:
            raise LlamaNotReadyError(f"modelo no disponible: {response.text[:200]}")
    if response.status_code >= 400:
        snippet = (response.text or "")[:400]
        logger.error(
            "[LLAMA] http_error status=%s body=%s",
            response.status_code,
            snippet,
        )
    response.raise_for_status()


def call_llama_local(
    prompt: str,
    context: str = "",
    *,
    system: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
) -> str:
    """Llamada simple (prompt único) — compatible con el snippet del usuario."""
    sys_text = (system or LLAMA_CONVERSATIONAL_SYSTEM).strip()
    full_prompt = prompt.strip()
    if context.strip():
        full_prompt = f"{context.strip()}\n\n{full_prompt}"
    payload: dict[str, Any] = {
        "model": llama_model(),
        "prompt": full_prompt,
        "system": sys_text,
        "stream": False,
        "keep_alive": _OLLAMA_KEEP_ALIVE,
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }
    if not llama_model_ready():
        raise LlamaNotReadyError(f"modelo {llama_model()} no descargado en Ollama")
    started = time.monotonic()
    with httpx.Client(timeout=_DEFAULT_TIMEOUT_SEC) as client:
        response = client.post(_generate_url(), json=payload)
        _raise_if_llama_http_error(response)
        _log_queue_wait(started, endpoint="generate")
        data = response.json()
    text = str(data.get("response") or "").strip()
    if not text:
        raise RuntimeError("Llama devolvió respuesta vacía")
    return text


def _messages_to_ollama(
    system: str,
    messages: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Convierte mensajes chat (user/assistant) al formato Ollama."""
    ollama_msgs: list[dict[str, str]] = []
    sys_clean = (system or LLAMA_CONVERSATIONAL_SYSTEM).strip()
    if sys_clean:
        ollama_msgs.append({"role": "system", "content": sys_clean})
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        if role == "user":
            ollama_msgs.append({"role": "user", "content": content.strip()})
        elif role in ("assistant", "model"):
            ollama_msgs.append({"role": "assistant", "content": content.strip()})
    return ollama_msgs


def call_llama_chat(
    *,
    system: str,
    messages: list[dict[str, Any]],
    temperature: float = 0.7,
    max_tokens: int = 2048,
    model: str | None = None,
    timeout_sec: float | None = None,
    num_ctx: int | None = None,
    endpoint_base: str | None = None,
) -> str:
    """Chat multi-turno — usado por text_chat y chats dedicados."""
    base = endpoint_base or _ollama_base()
    target_model = (model or llama_model()).strip()
    http_timeout = timeout_sec if timeout_sec is not None else _CHAT_TIMEOUT_SEC
    ollama_msgs = _messages_to_ollama(system, messages)
    if not any(m["role"] == "user" for m in ollama_msgs):
        raise RuntimeError("Sin mensajes de usuario para Llama")
    options: dict[str, Any] = {"temperature": temperature, "num_predict": max_tokens}
    if num_ctx is not None:
        options["num_ctx"] = num_ctx
    payload: dict[str, Any] = {
        "model": target_model,
        "messages": ollama_msgs,
        "stream": False,
        "keep_alive": _OLLAMA_KEEP_ALIVE,
        "options": options,
    }
    if not _cached_model_ready(model_name=target_model, base=base, timeout_sec=_HEALTH_TIMEOUT_SEC):
        raise LlamaNotReadyError(f"modelo {target_model} no descargado en Ollama")
    started = time.monotonic()
    with httpx.Client(timeout=http_timeout) as client:
        response = client.post(_chat_url(base=base), json=payload)
        _raise_if_llama_http_error(response)
        _log_queue_wait(started, endpoint=f"chat:{target_model}")
        data = response.json()
    msg = data.get("message") or {}
    text = str(msg.get("content") or "").strip()
    if not text:
        text = str(msg.get("thinking") or "").strip()
    if not text:
        logger.error(
            "[LLAMA] empty_reply model=%s done=%s eval_count=%s prompt_eval=%s msg_keys=%s",
            target_model,
            data.get("done"),
            data.get("eval_count"),
            data.get("prompt_eval_count"),
            list(msg.keys()) if isinstance(msg, dict) else type(msg).__name__,
        )
        raise RuntimeError("Llama devolvió respuesta vacía")
    return text


def call_llama_voice_generate(
    *,
    system: str,
    user_text: str,
    temperature: float = 0.55,
    max_tokens: int = 140,
    timeout_sec: float = 12.0,
) -> str:
    """Generación casual de voz — modelo 3B con varias estrategias ante OOM en prod."""
    voice = llama_voice_model()
    if not llama_voice_model_ready():
        raise LlamaNotReadyError(f"modelo {voice} no descargado en Ollama")

    voice_base = _ollama_voice_base()
    text_model = llama_model()
    if not llama_voice_endpoint_separate() and text_model != voice:
        _ollama_unload_model(text_model, base=voice_base)

    sys_clean = system.strip()
    prompt = user_text.strip()
    options = {"temperature": temperature, "num_predict": max_tokens}

    inline_prompt = (
        f"Instrucciones del sistema:\n{sys_clean}\n\n"
        f"Usuario: {prompt}\n\n"
        "Asistente:"
    )

    attempts: list[tuple[str, str, dict[str, Any], Any]] = [
        (
            "generate_inline",
            _voice_generate_url(),
            {
                "model": voice,
                "prompt": inline_prompt,
                "stream": False,
                "keep_alive": "30m",
                "options": options,
            },
            _parse_generate_response,
        ),
    ]

    last_exc: Exception | None = None
    last_body = ""
    started = time.monotonic()
    per_attempt_timeout = max(timeout_sec, 8.0)
    for idx, (label, url, payload, parser) in enumerate(attempts):
        if idx > 0 and not llama_voice_endpoint_separate() and text_model != voice:
            _ollama_unload_model(text_model, base=voice_base)
        try:
            with httpx.Client(timeout=per_attempt_timeout) as client:
                response = client.post(url, json=payload)
                if response.status_code >= 400:
                    last_body = (response.text or "")[:400]
                _raise_if_llama_http_error(response)
                _log_queue_wait(started, endpoint=f"voice:{voice}:{label}")
                text = parser(response.json())
            if text:
                return text
            logger.error(
                "[LLAMA] empty_voice_reply model=%s strategy=%s",
                voice,
                label,
            )
        except httpx.HTTPStatusError as exc:
            last_exc = exc
            last_body = (exc.response.text or "")[:400]
            logger.warning(
                "[LLAMA] voice_attempt_failed model=%s strategy=%s status=%s body=%s",
                voice,
                label,
                exc.response.status_code,
                last_body,
            )
            continue
        except httpx.TimeoutException as exc:
            last_exc = exc
            logger.warning(
                "[LLAMA] voice_attempt_timeout model=%s strategy=%s",
                voice,
                label,
            )
            continue
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.warning(
                "[LLAMA] voice_attempt_failed model=%s strategy=%s err=%s",
                voice,
                label,
                exc,
            )
            continue

    if last_exc:
        if last_body and isinstance(last_exc, httpx.HTTPStatusError):
            raise RuntimeError(f"{last_exc}; ollama_body={last_body}") from last_exc
        raise last_exc
    raise RuntimeError("Llama devolvió respuesta vacía")


def call_llama_voice_chat(
    *,
    system: str,
    messages: list[dict[str, Any]],
    temperature: float = 0.7,
    max_tokens: int = 1024,
    timeout_sec: float | None = None,
    num_ctx: int | None = None,
) -> str:
    """Chat de voz — usa modelo liviano (3B) con timeout acorde."""
    voice = llama_voice_model()
    http_timeout = timeout_sec if timeout_sec is not None else _VOICE_CHAT_TIMEOUT_SEC
    if not llama_voice_model_ready():
        logger.warning("[LLAMA] voice model %s no listo — fallback a %s", voice, llama_model())
        return call_llama_chat(
            system=system,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout_sec=http_timeout,
            num_ctx=num_ctx,
        )
    return call_llama_chat(
        system=system,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        model=voice,
        timeout_sec=http_timeout,
        num_ctx=num_ctx,
        endpoint_base=_ollama_voice_base(),
    )


def iter_llama_chat_stream(
    *,
    system: str,
    messages: list[dict[str, Any]],
    temperature: float = 0.7,
    max_tokens: int = 2048,
    model: str | None = None,
    timeout_sec: float | None = None,
    endpoint_base: str | None = None,
) -> Iterator[str]:
    """Streaming token a token para SSE de chats — siempre deltas incrementales."""
    from app.services.stream_delta import stream_piece_delta

    base = endpoint_base or _ollama_base()
    target_model = (model or llama_model()).strip()
    http_timeout = timeout_sec if timeout_sec is not None else _CHAT_TIMEOUT_SEC
    ollama_msgs = _messages_to_ollama(system, messages)
    if not any(m["role"] == "user" for m in ollama_msgs):
        raise RuntimeError("Sin mensajes de usuario para Llama")
    payload: dict[str, Any] = {
        "model": target_model,
        "messages": ollama_msgs,
        "stream": True,
        "keep_alive": _OLLAMA_KEEP_ALIVE,
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }
    if not _cached_model_ready(model_name=target_model, base=base, timeout_sec=_HEALTH_TIMEOUT_SEC):
        raise LlamaNotReadyError(f"modelo {target_model} no descargado en Ollama")
    accumulated = ""
    started = time.monotonic()
    queue_logged = False
    with httpx.Client(timeout=http_timeout) as client:
        with client.stream("POST", _chat_url(base=base), json=payload) as response:
            _raise_if_llama_http_error(response)
            for line in response.iter_lines():
                if not queue_logged and line:
                    _log_queue_wait(started, endpoint=f"chat_stream:{target_model}")
                    queue_logged = True
                if not line:
                    continue
                import json

                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = chunk.get("message") or {}
                piece = str(msg.get("content") or "")
                delta = stream_piece_delta(accumulated, piece)
                if delta:
                    accumulated += delta
                    yield delta
                if chunk.get("done"):
                    break


def iter_llama_voice_chat_stream(
    *,
    system: str,
    messages: list[dict[str, Any]],
    temperature: float = 0.7,
    max_tokens: int = 1024,
) -> Iterator[str]:
    """Streaming para voz Retell — modelo liviano 3B."""
    voice = llama_voice_model()
    if llama_voice_model_ready():
        yield from iter_llama_chat_stream(
            system=system,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            model=voice,
            timeout_sec=_VOICE_CHAT_TIMEOUT_SEC,
            endpoint_base=_ollama_voice_base(),
        )
        return
    logger.warning("[LLAMA] voice stream fallback to %s", llama_model())
    yield from iter_llama_chat_stream(
        system=system,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
