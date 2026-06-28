"""Tests — búsqueda web en chat de texto alineada con voz."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import patch

from app.services.gemini_grounded import SEARCH_WEB_TIMEOUT_SEC, execute_search_web
from app.services.text_chat import (
    CHAT_SYSTEM_BASE,
    CHAT_TOOLS,
    _promised_web_search_without_tool,
    _run_chat_tool,
)


def test_chat_text_uses_parallel_search():
    async def fake_parallel(query: str, *, kind: str = "general"):
        return {
            "ok": True,
            "summary": "Datos recientes sobre el terremoto en Venezuela.",
            "source": "tavily",
        }

    with patch(
        "app.services.gemini_grounded.fetch_voice_brief_parallel",
        side_effect=fake_parallel,
    ):
        result = _run_chat_tool(
            "user-chat-search",
            "search_web",
            {"query": "muertes terremoto Venezuela", "kind": "news"},
        )

    import json

    data = json.loads(result)
    assert data.get("ok") is True
    assert data.get("status") == "success"
    assert "terremoto" in data.get("summary", "").lower()


def test_chat_text_search_web_timeout_17s():
    async def slow_parallel(*_a, **_k):
        await asyncio.sleep(SEARCH_WEB_TIMEOUT_SEC + 2)
        return {"ok": True, "summary": "nunca debería llegar"}

    async def run() -> dict:
        with patch(
            "app.services.gemini_grounded.fetch_voice_brief_parallel",
            side_effect=slow_parallel,
        ):
            return await execute_search_web("clima Caracas", kind="weather")

    started = time.monotonic()
    result = asyncio.run(run())
    elapsed = time.monotonic() - started

    assert result.get("ok") is False
    assert result.get("status") == "timeout"
    assert result.get("fallback") is True
    assert elapsed < SEARCH_WEB_TIMEOUT_SEC + 3


def test_chat_text_invokes_tool_not_hallucinates():
    tool_names = {t["name"] for t in CHAT_TOOLS}
    assert "search_web" in tool_names

    assert "NUNCA digas" in CHAT_SYSTEM_BASE and "search_web" in CHAT_SYSTEM_BASE
    assert "voy a buscar" in CHAT_SYSTEM_BASE.lower()

    assert _promised_web_search_without_tool("Voy a buscar esa información para usted.")
    assert not _promised_web_search_without_tool(
        "Según reportes recientes, el terremoto dejó más de cien víctimas en la región."
    )
