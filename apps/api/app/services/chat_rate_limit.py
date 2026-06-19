"""Rate limit por minuto para chat de texto — token bucket con ráfaga."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from threading import Lock

# 60 mensajes/min con ráfaga de 20 (1 token/s de recarga).
_BURST_CAPACITY = 20.0
_REFILL_PER_SEC = 1.0  # 60/min
_ADMIN_REFILL_PER_SEC = 3.33  # ~200/min efectivo para admins


@dataclass
class _BucketState:
    tokens: float
    updated_at: float


_lock = Lock()
_buckets: dict[str, _BucketState] = {}


def _capacity(*, is_admin: bool) -> float:
    return _BURST_CAPACITY if not is_admin else _BURST_CAPACITY * 2


def _refill_rate(*, is_admin: bool) -> float:
    return _ADMIN_REFILL_PER_SEC if is_admin else _REFILL_PER_SEC


def check_chat_rate_limit(user_id: str, *, is_admin: bool) -> tuple[bool, int]:
    """
    Devuelve (permitido, segundos_de_espera).
    Admins tienen cupo alto (~200/min); usuarios normales 60/min con ráfaga 20.
    """
    uid = (user_id or "").strip()
    if not uid:
        return True, 0

    now = time.monotonic()
    cap = _capacity(is_admin=is_admin)
    rate = _refill_rate(is_admin=is_admin)

    with _lock:
        state = _buckets.get(uid)
        if state is None:
            state = _BucketState(tokens=cap, updated_at=now)
            _buckets[uid] = state

        elapsed = max(0.0, now - state.updated_at)
        state.tokens = min(cap, state.tokens + elapsed * rate)
        state.updated_at = now

        if state.tokens >= 1.0:
            state.tokens -= 1.0
            return True, 0

        deficit = 1.0 - state.tokens
        retry = max(1, min(30, int(math.ceil(deficit / rate))))
        return False, retry
