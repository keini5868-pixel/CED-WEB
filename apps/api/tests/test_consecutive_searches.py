"""Tests — búsquedas consecutivas sin leak de tasks ni conexiones."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import httpx

from app.services.gemini_grounded import (
    _cleanup_search_tasks,
    _log_active_search_tasks,
    execute_search_web,
    execute_search_web_sync,
    fetch_voice_brief_parallel,
)

VALID_BRIEF = (
    "Según reportes recientes, el terremoto dejó varias víctimas en la región, señor."
)


def _search_settings() -> MagicMock:
    settings = MagicMock()
    settings.tavily_api_key = "tvly-test"
    settings.google_api_key = ""
    return settings


@contextmanager
def _mock_fast_tavily():
    async def fast_tavily(_topic: str, _kind: str) -> str:
        await asyncio.sleep(0.01)
        return VALID_BRIEF

    with (
        patch("app.services.gemini_grounded.get_settings", return_value=_search_settings()),
        patch("app.services.gemini_grounded._run_tavily_async", side_effect=fast_tavily),
        patch("app.services.gemini_grounded._run_gemini_async", return_value=""),
    ):
        yield


def test_five_consecutive_searches_no_leak():
    async def run() -> int:
        with _mock_fast_tavily():
            for i in range(5):
                result = await execute_search_web(f"consulta consecutiva {i}", kind="news")
                assert result.get("ok") is True or result.get("fallback") is True
            _log_active_search_tasks()
            return sum(
                1
                for t in asyncio.all_tasks()
                if t.get_name().startswith(("tavily_", "gemini_"))
            )

    leftover = asyncio.run(run())
    assert leftover == 0


def test_search_tasks_cleaned_after_each_query():
    cancelled: list[str] = []

    async def slow_gemini(_topic: str, _kind: str, _key: str) -> str:
        try:
            await asyncio.sleep(2.0)
        except asyncio.CancelledError:
            cancelled.append("gemini")
            raise
        return VALID_BRIEF

    async def fast_tavily(_topic: str, _kind: str) -> str:
        await asyncio.sleep(0.01)
        return VALID_BRIEF

    settings = _search_settings()
    settings.google_api_key = "google-test"

    async def run() -> None:
        with (
            patch("app.services.gemini_grounded.get_settings", return_value=settings),
            patch("app.services.gemini_grounded._run_tavily_async", side_effect=fast_tavily),
            patch("app.services.gemini_grounded._run_gemini_async", side_effect=slow_gemini),
        ):
            for i in range(3):
                result = await fetch_voice_brief_parallel(f"query {i}", kind="general")
                assert result.get("ok") is True
                active = [
                    t
                    for t in asyncio.all_tasks()
                    if t.get_name().startswith(("tavily_", "gemini_"))
                ]
                assert active == [], f"tasks residuales tras búsqueda {i}: {active}"

    asyncio.run(run())
    assert "gemini" in cancelled


def test_httpx_connections_closed_after_search():
    enter_count = {"n": 0}
    exit_count = {"n": 0}

    class TrackingClient(httpx.Client):
        def __enter__(self):
            enter_count["n"] += 1
            return super().__enter__()

        def __exit__(self, *args):
            exit_count["n"] += 1
            return super().__exit__(*args)

    with patch("app.services.tavily_search.httpx.Client", TrackingClient):
        from app.services.tavily_search import tavily_raw_search

        with patch.object(TrackingClient, "post") as mock_post:
            mock_post.return_value = MagicMock(
                status_code=200,
                json=lambda: {"answer": "ok", "results": [], "response_time": 0.1},
            )
            tavily_raw_search("test query")

    assert enter_count["n"] == 1
    assert exit_count["n"] == 1


def test_execute_search_web_sync_five_times_no_hang():
    with _mock_fast_tavily():
        for i in range(5):
            result = execute_search_web_sync(f"sync query {i}", kind="news")
            assert result.get("ok") is True or result.get("fallback") is True


def test_cleanup_search_tasks_cancels_pending():
    async def run() -> None:
        async def sleeper() -> str:
            await asyncio.sleep(5)
            return "late"

        task = asyncio.create_task(sleeper())
        task.set_name("gemini_test")
        await _cleanup_search_tasks([task])
        assert task.cancelled() or task.done()

    asyncio.run(run())


def test_run_gemini_returns_after_timeout_when_brief_hangs():
    import time

    from app.services.gemini_grounded import GEMINI_TIMEOUT_SEC, _run_gemini

    def slow_brief(*_args, **_kwargs) -> str:
        time.sleep(GEMINI_TIMEOUT_SEC + 30)
        return "never"

    start = time.perf_counter()
    with patch("app.services.gemini_grounded._generate_brief", side_effect=slow_brief):
        result = _run_gemini("noticias hoy", "news", "fake-key")
    elapsed = time.perf_counter() - start

    assert result == ""
    assert elapsed < GEMINI_TIMEOUT_SEC + 4
