"""Tests — search_web timeout y fallback explícito."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from app.services.voice_tool_executor import SEARCH_WEB_TIMEOUT_SEC, execute_voice_tool


def test_search_web_timeout_returns_fallback():
    async def slow_brief(*_args, **_kwargs):
        await asyncio.sleep(SEARCH_WEB_TIMEOUT_SEC + 2)
        return {"ok": True, "summary": "resultado tardío"}

    with patch("app.services.voice_tool_executor.fetch_voice_brief_parallel", slow_brief):
        result = asyncio.run(
            execute_voice_tool(
                "search_web",
                "user-test-123",
                {"query": "clima en Caracas hoy", "kind": "weather"},
            )
        )

    assert result.get("status") == "timeout"
    assert result.get("fallback") is True
    assert result.get("spoken")


def test_search_web_empty_result_returns_fallback():
    async def empty_brief(*_a, **_k):
        return {"ok": False, "error": "vacío", "code": "empty_result"}

    with patch(
        "app.services.voice_tool_executor.fetch_voice_brief_parallel",
        side_effect=empty_brief,
    ):
        result = asyncio.run(
            execute_voice_tool(
                "search_web",
                "user-test-123",
                {"query": "noticias de Venezuela hoy", "kind": "news"},
            )
        )

    assert result.get("status") == "timeout"
    assert result.get("fallback") is True


def test_search_web_success_returns_status_success():
    async def ok_brief(*_a, **_k):
        return {
            "ok": True,
            "summary": "El clima en Caracas hoy es soleado, señor.",
            "source": "tavily",
        }

    with patch(
        "app.services.voice_tool_executor.fetch_voice_brief_parallel",
        side_effect=ok_brief,
    ):
        result = asyncio.run(
            execute_voice_tool(
                "search_web",
                "user-test-123",
                {"query": "clima en Caracas hoy", "kind": "weather"},
            )
        )

    assert result.get("status") == "success"
    assert result.get("ok") is True
    assert "soleado" in result.get("spoken", "")
