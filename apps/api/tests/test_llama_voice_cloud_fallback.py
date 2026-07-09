"""Tests — voz Llama con fallback cloud."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from app.services.llama_voice_llm import LlamaVoiceLlm, FALLBACK_REPLY


def test_llama_reply_uses_cloud_when_llama_fails():
    llm = LlamaVoiceLlm()
    llm.set_latency_context("test-call", 1)

    async def run() -> str:
        with patch(
            "app.services.llama_voice_llm.call_llama_chat",
            side_effect=RuntimeError("llama down"),
        ), patch(
            "app.services.cloud_llm_fallback.chat_cloud_reply",
            return_value="La creatina es un suplemento para rendimiento deportivo.",
        ):
            return await llm._llama_reply(
                system="sys",
                messages=[{"role": "user", "content": "qué es la creatina"}],
                user_text="qué es la creatina",
            )

    reply = asyncio.run(run())
    assert "creatina" in reply.lower()


def test_llama_reply_returns_fallback_when_all_fail():
    llm = LlamaVoiceLlm()
    llm.set_latency_context("test-call", 1)

    async def run() -> str:
        with patch(
            "app.services.llama_voice_llm.call_llama_chat",
            side_effect=RuntimeError("llama down"),
        ), patch(
            "app.services.cloud_llm_fallback.chat_cloud_reply",
            return_value=None,
        ):
            return await llm._llama_reply(
                system="sys",
                messages=[{"role": "user", "content": "hola"}],
            )

    reply = asyncio.run(run())
    assert reply == FALLBACK_REPLY
