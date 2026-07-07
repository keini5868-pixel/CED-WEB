"""Tests — trabajo sync fuera del event loop."""

from __future__ import annotations

import asyncio

from app.services.async_sync import run_sync


def test_run_sync_executes_in_thread():
    async def _run() -> int:
        return await run_sync(lambda: 40 + 2)

    assert asyncio.run(_run()) == 42
