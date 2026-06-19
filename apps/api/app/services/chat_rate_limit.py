"""Rate limit por minuto para chat de texto — token bucket con ráfaga."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from threading import Lock

# 100 mensajes/min, ráfaga 30 (≈1.67 tokens/s).
_MAX_REQUESTS = 100
_WINDOW_SECONDS = 60
_BURST_CAPACITY = 30.0
_REFILL_PER_SEC = _MAX_REQUESTS / _WINDOW_SECONDS


@dataclass
class _BucketState:
    tokens: float
    updated_at: float


_lock = Lock()
_buckets: dict[str, _BucketState] = {}


def check_chat_rate_limit(user_id: str, *, is_admin: bool, unlimited_plan: bool) -> tuple[bool, int]:
    """Devuelve (permitido, segundos_de_espera). Admin e ilimitados: sin límite."""
    if is_admin or unlimited_plan:
        return True, 0

    uid = (user_id or "").strip()
    if not uid:
        return True, 0

    now = time.monotonic()
    cap = _BURST_CAPACITY + _REFILL_PER_SEC * _WINDOW_SECONDS  # hasta 100 en ventana

    with _lock:
        state = _buckets.get(uid)
        if state is None:
            state = _BucketState(tokens=cap, updated_at=now)
            _buckets[uid] = state

        elapsed = max(0.0, now - state.updated_at)
        state.tokens = min(cap, state.tokens + elapsed * _REFILL_PER_SEC)
        state.updated_at = now

        if state.tokens >= 1.0:
            state.tokens -= 1.0
            return True, 0

        deficit = 1.0 - state.tokens
        retry = max(1, min(30, int(math.ceil(deficit / _REFILL_PER_SEC))))
        return False, retry
