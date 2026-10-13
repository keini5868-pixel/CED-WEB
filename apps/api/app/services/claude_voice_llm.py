"""Claude Haiku — cerebro Retell Custom LLM (Messages API + tools de voz)."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from app.config import get_settings
from app.services.http_clients import get_openai_async_client
from app.services.openai_voice_llm import OpenAIVoiceLlm
from app.services.text_chat import CHAT_MODEL_FAST
from app.services.voice_llm_common import prompt_sha_prefix

logger = logging.getLogger(__name__)

ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
PROVIDER = "claude"


def _voice_model() -> str:
    settings = get_settings()
    model = (getattr(settings, "anthropic_model_retell_llm", None) or "").strip()
    return model or CHAT_MODEL_FAST


def _api_key() -> str:
    key = (get_settings().anthropic_api_key or "").strip()
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY no configurada")
    return key


def _openai_tools_to_anthropic(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for tool in tools:
        fn = tool.get("function") if isinstance(tool.get("function"), dict) else tool
        name = str((fn or {}).get("name") or tool.get("name") or "").strip()
        if not name:
            continue
        out.append(
            {
                "name": name,
                "description": str((fn or {}).get("description") or tool.get("description") or ""),
                "input_schema": (fn or {}).get("parameters")
                or tool.get("input_schema")
                or {"type": "object", "properties": {}},
            }
        )
    return out


def _openai_messages_to_anthropic(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convierte historial OpenAI (incl. tool) al formato Messages API."""
    rows: list[dict[str, Any]] = []
    pending_tool_results: list[dict[str, Any]] = []

    def flush_tools() -> None:
        nonlocal pending_tool_results
        if not pending_tool_results:
            return
        rows.append({"role": "user", "content": pending_tool_results})
        pending_tool_results = []

    for msg in messages:
        role = str(msg.get("role") or "").strip().lower()
        if role == "tool":
            pending_tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": str(msg.get("tool_call_id") or ""),
                    "content": str(msg.get("content") or ""),
                }
            )
            continue
        flush_tools()
        if role not in ("user", "assistant"):
            continue
        content = msg.get("content")
        if role == "assistant" and msg.get("tool_calls"):
            blocks: list[dict[str, Any]] = []
            if isinstance(content, str) and content.strip():
                blocks.append({"type": "text", "text": content.strip()})
            for tc in msg.get("tool_calls") or []:
                fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
                raw_args = fn.get("arguments") if isinstance(fn, dict) else "{}"
                try:
                    parsed = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                except json.JSONDecodeError:
                    parsed = {}
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": str(tc.get("id") or ""),
                        "name": str(fn.get("name") or ""),
                        "input": parsed if isinstance(parsed, dict) else {},
                    }
                )
            rows.append({"role": "assistant", "content": blocks or ""})
            continue
        text = content if isinstance(content, str) else str(content or "")
        if text.strip():
            rows.append({"role": role, "content": text.strip()})
    flush_tools()
    return rows


def _anthropic_response_to_openai(data: dict[str, Any]) -> dict[str, Any]:
    blocks = data.get("content") or []
    text_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            text_parts.append(str(block.get("text") or ""))
        elif block.get("type") == "tool_use":
            tool_calls.append(
                {
                    "id": str(block.get("id") or ""),
                    "type": "function",
                    "function": {
                        "name": str(block.get("name") or ""),
                        "arguments": json.dumps(block.get("input") or {}, ensure_ascii=False),
                    },
                }
            )
    message: dict[str, Any] = {}
    if text_parts:
        message["content"] = "".join(text_parts).strip()
    if tool_calls:
        message["tool_calls"] = tool_calls
    if not message:
        message["content"] = ""
    return {"choices": [{"message": message}]}


class ClaudeVoiceLlm(OpenAIVoiceLlm):
    """Misma orquestación que OpenAI; llamadas a Anthropic Haiku."""

    def __init__(self) -> None:
        super().__init__()
        self.model = _voice_model()

    async def _chat_completion(
        self,
        *,
        messages: list[dict[str, Any]],
        system: str,
        path: str,
        timeout_sec: float,
        max_tokens: int = 640,
        temperature: float = 0.4,
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        from app.services.voice_latency import get_turn

        turn = (
            get_turn(self._latency_call_id, self._latency_response_id)
            if self._latency_call_id and self._latency_response_id
            else None
        )
        if turn:
            turn.mark_llm_request(path=path)

        logger.info(
            "[RETELL-CLAUDE] model_call start path=%s model=%s prompt_sha=%s user=%s ts=%.3f",
            path,
            self.model,
            prompt_sha_prefix(),
            (self.user_id or "?")[:8],
            time.time(),
        )

        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": (system or "").strip(),
            "messages": _openai_messages_to_anthropic(messages),
        }
        if tools:
            payload["tools"] = _openai_tools_to_anthropic(tools)

        headers = {
            "x-api-key": _api_key(),
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        client = get_openai_async_client()
        res = await client.post(
            ANTHROPIC_MESSAGES_URL,
            headers=headers,
            json=payload,
            timeout=timeout_sec + 2.0,
        )
        if res.status_code >= 400:
            logger.warning(
                "[RETELL-CLAUDE] model_call error path=%s status=%s body=%s",
                path,
                res.status_code,
                res.text[:400],
            )
            res.raise_for_status()
        data = res.json()
        if turn:
            turn.mark_llm_first_token()
        logger.info(
            "[RETELL-CLAUDE] model_call done path=%s model=%s user=%s",
            path,
            self.model,
            (self.user_id or "?")[:8],
        )
        return _anthropic_response_to_openai(data)
