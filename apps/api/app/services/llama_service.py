"""Cerebro conversacional local vía Ollama (Llama).

Reemplaza Gemini para generación de texto en todos los canales excepto Chat Avanzado
(Claude). Sin function-calling autónomo: el orquestador determinista ejecuta módulos.
"""

from __future__ import annotations

import logging
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
_CHAT_TIMEOUT_SEC = 8.0
_HEALTH_TIMEOUT_SEC = 3.0
_MODEL_READY_CACHE_TTL_SEC = 15.0
_CHAT_HEALTH_TIMEOUT_SEC = 2.0

_model_ready_cache: tuple[float, bool] | None = None


class LlamaNotReadyError(RuntimeError):
    """Ollama responde pero el modelo configurado no está descargado."""


def _ollama_base() -> str:
    endpoint = get_settings().llama_endpoint.strip()
    if not endpoint:
        return "http://localhost:11434"
    # Acepta URL completa (/api/generate o /api/chat) o solo host:puerto.
    for suffix in ("/api/generate", "/api/chat", "/api/tags"):
        if endpoint.endswith(suffix):
            return endpoint[: -len(suffix)]
    return endpoint.rstrip("/")


def _chat_url() -> str:
    return f"{_ollama_base()}/api/chat"


def _generate_url() -> str:
    return f"{_ollama_base()}/api/generate"


def _tags_url() -> str:
    return f"{_ollama_base()}/api/tags"


def llama_model() -> str:
    return (get_settings().llama_model or "llama2:13b").strip() or "llama2:13b"


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
    """Diagnóstico detallado para /health — expone URL, error y modelos."""
    url = _tags_url()
    base = _ollama_base()
    result: dict[str, Any] = {
        "url": url,
        "endpoint": base,
        "model": llama_model(),
        "timeout_sec": _HEALTH_TIMEOUT_SEC,
        "ok": False,
    }
    try:
        import time

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
        logger.warning("[LLAMA] health check failed url=%s err=%s", url, exc)
    return result


def llama_model_ready(*, force_refresh: bool = False, timeout_sec: float | None = None) -> bool:
    """True si Ollama tiene el modelo configurado (no solo el daemon)."""
    global _model_ready_cache
    import time

    now = time.monotonic()
    if (
        not force_refresh
        and timeout_sec is None
        and _model_ready_cache is not None
        and now - _model_ready_cache[0] < _MODEL_READY_CACHE_TTL_SEC
    ):
        return _model_ready_cache[1]
    probe_timeout = timeout_sec if timeout_sec is not None else _HEALTH_TIMEOUT_SEC
    ready = bool(_llama_health_model_ready(timeout_sec=probe_timeout))
    if timeout_sec is None:
        _model_ready_cache = (now, ready)
    return ready


def _llama_health_model_ready(*, timeout_sec: float) -> bool:
    url = _tags_url()
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
        target = llama_model()
        return target in names or any(target.split(":")[0] in n for n in names)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[LLAMA] health check failed url=%s err=%s", url, exc)
        return False


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


def _raise_if_llama_http_error(response: httpx.Response) -> None:
    if response.status_code == 404:
        body = response.text.lower()
        if "not found" in body or "model" in body:
            raise LlamaNotReadyError(f"modelo no disponible: {response.text[:200]}")
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
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }
    if not llama_model_ready():
        raise LlamaNotReadyError(f"modelo {llama_model()} no descargado en Ollama")
    with httpx.Client(timeout=_DEFAULT_TIMEOUT_SEC) as client:
        response = client.post(_generate_url(), json=payload)
        _raise_if_llama_http_error(response)
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
) -> str:
    """Chat multi-turno — usado por text_chat y chats dedicados."""
    ollama_msgs = _messages_to_ollama(system, messages)
    if not any(m["role"] == "user" for m in ollama_msgs):
        raise RuntimeError("Sin mensajes de usuario para Llama")
    payload: dict[str, Any] = {
        "model": llama_model(),
        "messages": ollama_msgs,
        "stream": False,
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }
    if not llama_model_ready():
        raise LlamaNotReadyError(f"modelo {llama_model()} no descargado en Ollama")
    with httpx.Client(timeout=_CHAT_TIMEOUT_SEC) as client:
        response = client.post(_chat_url(), json=payload)
        _raise_if_llama_http_error(response)
        data = response.json()
    msg = data.get("message") or {}
    text = str(msg.get("content") or "").strip()
    if not text:
        raise RuntimeError("Llama devolvió respuesta vacía")
    return text


def iter_llama_chat_stream(
    *,
    system: str,
    messages: list[dict[str, Any]],
    temperature: float = 0.7,
    max_tokens: int = 2048,
) -> Iterator[str]:
    """Streaming token a token para SSE de chats — siempre deltas incrementales."""
    from app.services.stream_delta import stream_piece_delta

    ollama_msgs = _messages_to_ollama(system, messages)
    if not any(m["role"] == "user" for m in ollama_msgs):
        raise RuntimeError("Sin mensajes de usuario para Llama")
    payload: dict[str, Any] = {
        "model": llama_model(),
        "messages": ollama_msgs,
        "stream": True,
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }
    if not llama_model_ready():
        raise LlamaNotReadyError(f"modelo {llama_model()} no descargado en Ollama")
    accumulated = ""
    with httpx.Client(timeout=_CHAT_TIMEOUT_SEC) as client:
        with client.stream("POST", _chat_url(), json=payload) as response:
            _raise_if_llama_http_error(response)
            for line in response.iter_lines():
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
