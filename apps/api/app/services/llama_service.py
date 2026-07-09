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
_HEALTH_TIMEOUT_SEC = 5.0


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


def llama_available() -> bool:
    """Ping rápido a Ollama — para /health y arranque."""
    try:
        with httpx.Client(timeout=_HEALTH_TIMEOUT_SEC) as client:
            r = client.get(_tags_url())
            return r.status_code == 200
    except Exception:  # noqa: BLE001
        return False


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
    with httpx.Client(timeout=_DEFAULT_TIMEOUT_SEC) as client:
        response = client.post(_generate_url(), json=payload)
        response.raise_for_status()
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
    with httpx.Client(timeout=_DEFAULT_TIMEOUT_SEC) as client:
        response = client.post(_chat_url(), json=payload)
        response.raise_for_status()
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
    """Streaming token a token para SSE de chats."""
    ollama_msgs = _messages_to_ollama(system, messages)
    if not any(m["role"] == "user" for m in ollama_msgs):
        raise RuntimeError("Sin mensajes de usuario para Llama")
    payload: dict[str, Any] = {
        "model": llama_model(),
        "messages": ollama_msgs,
        "stream": True,
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }
    with httpx.Client(timeout=_DEFAULT_TIMEOUT_SEC) as client:
        with client.stream("POST", _chat_url(), json=payload) as response:
            response.raise_for_status()
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
                if piece:
                    yield piece
                if chunk.get("done"):
                    break
