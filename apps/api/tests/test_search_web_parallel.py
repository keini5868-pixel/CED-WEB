"""Tests — paralelismo Tavily/Gemini y anti-doble-respuesta."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from app.services.gemini_grounded import fetch_voice_brief_parallel
from app.services.voice_tool_executor import SearchWebState


TAVILY_TEXT = (
    "Cristiano Ronaldo sigue activo en 2026 con el Al Nassr y la selección de Portugal, señor."
)
GEMINI_TEXT = (
    "Gemini encontró noticias recientes sobre Cristiano Ronaldo en la liga saudí para 2026, señor."
)


def test_search_web_parallel_returns_first():
    async def fast_tavily(_topic: str, _kind: str) -> str:
        await asyncio.sleep(0.02)
        return TAVILY_TEXT

    async def slow_gemini(_topic: str, _kind: str, _key: str) -> str:
        await asyncio.sleep(0.5)
        return GEMINI_TEXT

    settings = MagicMock()
    settings.tavily_api_key = "tvly-test"
    settings.google_api_key = "google-test"

    async def run() -> dict:
        with (
            patch("app.services.gemini_grounded.get_settings", return_value=settings),
            patch("app.services.gemini_grounded._run_tavily_async", side_effect=fast_tavily),
            patch("app.services.gemini_grounded._run_gemini_async", side_effect=slow_gemini),
        ):
            return await fetch_voice_brief_parallel("Cristiano Ronaldo 2026", kind="general")

    result = asyncio.run(run())

    assert result.get("ok") is True
    assert result.get("source") == "tavily"
    assert "Cristiano Ronaldo" in result.get("summary", "")


def test_search_web_cancels_pending_task():
    cancelled: list[str] = []

    async def fast_tavily(_topic: str, _kind: str) -> str:
        await asyncio.sleep(0.02)
        return TAVILY_TEXT

    async def slow_gemini(_topic: str, _kind: str, _key: str) -> str:
        try:
            await asyncio.sleep(2.0)
        except asyncio.CancelledError:
            cancelled.append("gemini_task")
            raise
        return GEMINI_TEXT

    settings = MagicMock()
    settings.tavily_api_key = "tvly-test"
    settings.google_api_key = "google-test"

    async def run() -> dict:
        with (
            patch("app.services.gemini_grounded.get_settings", return_value=settings),
            patch("app.services.gemini_grounded._run_tavily_async", side_effect=fast_tavily),
            patch("app.services.gemini_grounded._run_gemini_async", side_effect=slow_gemini),
        ):
            return await fetch_voice_brief_parallel("Cristiano Ronaldo 2026", kind="general")

    result = asyncio.run(run())

    assert result.get("ok") is True
    assert result.get("source") == "tavily"
    assert "gemini_task" in cancelled


def test_search_web_no_duplicate_response():
    state = SearchWebState()
    first = state.take({"status": "success", "ok": True, "spoken": TAVILY_TEXT})
    second = state.take({"status": "success", "ok": True, "spoken": GEMINI_TEXT})

    assert first is not None
    assert first.get("spoken") == TAVILY_TEXT
    assert second is None
    assert state.responded is True
