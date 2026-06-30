"""Clientes HTTP compartidos — connection pooling para menor latencia."""

from __future__ import annotations

import atexit
import httpx

_OPENAI_LIMITS = httpx.Limits(max_connections=20, max_keepalive_connections=10)
_OPENAI_TIMEOUT = httpx.Timeout(30.0, connect=5.0)

_openai_async_client: httpx.AsyncClient | None = None


def get_openai_async_client() -> httpx.AsyncClient:
    global _openai_async_client
    if _openai_async_client is None or _openai_async_client.is_closed:
        _openai_async_client = httpx.AsyncClient(
            timeout=_OPENAI_TIMEOUT,
            limits=_OPENAI_LIMITS,
        )
    return _openai_async_client


async def aclose_http_clients() -> None:
    global _openai_async_client
    if _openai_async_client is not None and not _openai_async_client.is_closed:
        await _openai_async_client.aclose()
    _openai_async_client = None


def _shutdown_http_clients() -> None:
    try:
        import asyncio

        asyncio.run(aclose_http_clients())
    except Exception:  # noqa: BLE001
        pass


atexit.register(_shutdown_http_clients)
