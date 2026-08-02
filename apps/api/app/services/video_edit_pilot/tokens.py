"""Saldo de tokens Video Edit — DB + fallback en memoria (tests/piloto)."""

from __future__ import annotations

import logging
import threading
from datetime import date, datetime, timezone
from typing import Any
from uuid import uuid4

from app.domain.video_edit_economy import (
    VIDEO_EDIT_SOFT_CAP_RENDERS_PER_DAY,
    tokens_for_usd,
)

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_mem_balances: dict[str, int] = {}
_mem_renders_today: dict[str, tuple[str, int]] = {}  # user -> (YYYY-MM-DD, count)
_mem_ledger: list[dict[str, Any]] = []


def _today_key() -> str:
    return date.today().isoformat()


def get_token_balance(user_id: str) -> int:
    try:
        from app.services import supabase_db

        bal = supabase_db.get_video_edit_token_balance(user_id)
        if bal is not None:
            return int(bal)
    except Exception as exc:  # noqa: BLE001
        logger.debug("[VIDEO_EDIT] balance db miss: %s", exc)
    with _lock:
        return int(_mem_balances.get(user_id, 0))


def credit_tokens(
    user_id: str,
    tokens: int,
    *,
    reason: str = "purchase",
    metadata: dict[str, Any] | None = None,
) -> int:
    tokens = max(0, int(tokens))
    if tokens <= 0:
        return get_token_balance(user_id)
    try:
        from app.services import supabase_db

        new_bal = supabase_db.credit_video_edit_tokens(
            user_id,
            tokens,
            reason=reason,
            metadata=metadata or {},
        )
        if new_bal is not None:
            return int(new_bal)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[VIDEO_EDIT] credit db fail: %s", exc)
    with _lock:
        cur = int(_mem_balances.get(user_id, 0))
        nxt = cur + tokens
        _mem_balances[user_id] = nxt
        _mem_ledger.append(
            {
                "id": str(uuid4()),
                "user_id": user_id,
                "delta_tokens": tokens,
                "reason": reason,
                "metadata": metadata or {},
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        return nxt


def debit_tokens(
    user_id: str,
    tokens: int,
    *,
    reason: str = "render",
    duration_sec: int | None = None,
    job_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    tokens = max(0, int(tokens))
    if tokens <= 0:
        return {"ok": True, "charged_tokens": 0, "balance_tokens": get_token_balance(user_id)}

    try:
        from app.services import supabase_db

        result = supabase_db.debit_video_edit_tokens(
            user_id,
            tokens,
            reason=reason,
            duration_sec=duration_sec,
            job_id=job_id,
            metadata=metadata or {},
        )
        if result is not None:
            return result
    except Exception as exc:  # noqa: BLE001
        logger.warning("[VIDEO_EDIT] debit db fail: %s", exc)

    with _lock:
        cur = int(_mem_balances.get(user_id, 0))
        if cur < tokens:
            return {
                "ok": False,
                "charged_tokens": 0,
                "balance_tokens": cur,
                "code": "insufficient_tokens",
                "error": (
                    f"Saldo insuficiente: necesita {tokens} tokens "
                    f"y tiene {cur}. Compre un pack de video."
                ),
            }
        nxt = cur - tokens
        _mem_balances[user_id] = nxt
        _mem_ledger.append(
            {
                "id": str(uuid4()),
                "user_id": user_id,
                "delta_tokens": -tokens,
                "reason": reason,
                "duration_sec": duration_sec,
                "job_id": job_id,
                "metadata": metadata or {},
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        return {"ok": True, "charged_tokens": tokens, "balance_tokens": nxt}


def renders_today(user_id: str) -> int:
    db_n: int | None = None
    try:
        from app.services import supabase_db

        db_n = supabase_db.count_video_edit_jobs_today(user_id)
    except Exception:  # noqa: BLE001
        db_n = None
    with _lock:
        day, count = _mem_renders_today.get(user_id, (_today_key(), 0))
        mem = int(count) if day == _today_key() else 0
    if db_n is None:
        return mem
    return max(int(db_n), mem)


def record_render_attempt(user_id: str) -> int:
    """Incrementa contador diario (soft cap). Devuelve total del día."""
    try:
        from app.services import supabase_db

        # El insert del job ya cuenta; este helper es para memoria.
        n = supabase_db.count_video_edit_jobs_today(user_id)
        if n is not None:
            return int(n)
    except Exception:  # noqa: BLE001
        pass
    with _lock:
        day = _today_key()
        prev_day, count = _mem_renders_today.get(user_id, (day, 0))
        if prev_day != day:
            count = 0
        count += 1
        _mem_renders_today[user_id] = (day, count)
        return count


def soft_cap_remaining(user_id: str) -> int:
    used = renders_today(user_id)
    return max(0, VIDEO_EDIT_SOFT_CAP_RENDERS_PER_DAY - used)


def credit_from_pack_usd(user_id: str, amount_usd: float, *, metadata: dict | None = None) -> dict[str, Any]:
    tokens = tokens_for_usd(amount_usd)
    bal = credit_tokens(
        user_id,
        tokens,
        reason="stripe_pack",
        metadata={**(metadata or {}), "amount_usd": amount_usd},
    )
    return {"ok": True, "tokens_credited": tokens, "balance_tokens": bal}


def reset_memory_for_tests() -> None:
    with _lock:
        _mem_balances.clear()
        _mem_renders_today.clear()
        _mem_ledger.clear()
