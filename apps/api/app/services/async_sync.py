"""Ejecutar trabajo bloqueante (Supabase sync, etc.) fuera del event loop."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


async def run_sync(func: Callable[..., T], /, *args, **kwargs) -> T:
    """Delega a un thread — no bloquea el loop principal de uvicorn."""
    return await asyncio.to_thread(func, *args, **kwargs)
