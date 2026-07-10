"""Diagnóstico de esquema Supabase para finanzas personales."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_finance_ready_cache: tuple[float, bool, str | None] | None = None
_CACHE_TTL_SEC = 30.0


def _probe_finance_table() -> tuple[bool, str | None]:
    from app.services.supabase_client import service_role_configured

    if not service_role_configured():
        return False, "SUPABASE_SERVICE_ROLE_KEY no configurada en la API"

    try:
        from app.services.supabase_db import _client

        _client().table("finance_transactions").select("id").limit(1).execute()
        return True, None
    except Exception as exc:  # noqa: BLE001
        raw = str(exc)
        if "PGRST205" in raw or "finance_transactions" in raw:
            return False, (
                "Tabla public.finance_transactions ausente. "
                "Ejecute migraciones 021 y 022 en Supabase."
            )
        return False, raw[:240]


def finance_db_ready(*, force_refresh: bool = False) -> bool:
    import time

    global _finance_ready_cache
    now = time.monotonic()
    if (
        not force_refresh
        and _finance_ready_cache is not None
        and now - _finance_ready_cache[0] < _CACHE_TTL_SEC
    ):
        return _finance_ready_cache[1]

    ready, err = _probe_finance_table()
    _finance_ready_cache = (now, ready, err)
    if not ready and err:
        logger.warning("[FINANCE] schema not ready: %s", err)
    return ready


def finance_db_error() -> str | None:
    finance_db_ready()
    if _finance_ready_cache is None:
        return None
    return _finance_ready_cache[2]


def finance_db_diagnostics() -> dict[str, Any]:
    ready, err = _probe_finance_table()
    return {
        "ready": ready,
        "error": err,
        "table": "finance_transactions",
        "migrations": ["021_finance_transactions.sql", "022_finance_pending_payments.sql"],
    }
