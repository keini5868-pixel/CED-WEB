"""Agent ID Retell — env + caché en memoria tras bootstrap automático."""

from __future__ import annotations

import threading

from app.config import get_settings

_lock = threading.Lock()
_bootstrapped_agent_id: str | None = None
_last_bootstrap: dict | None = None
_last_bootstrap_error: str | None = None
_native_staging_agent_id: str | None = None
_last_native_staging: dict | None = None


def set_bootstrapped_agent(agent_id: str, meta: dict | None = None) -> None:
    global _bootstrapped_agent_id, _last_bootstrap, _last_bootstrap_error
    aid = (agent_id or "").strip()
    if not aid:
        return
    with _lock:
        _bootstrapped_agent_id = aid
        _last_bootstrap = meta or {"agent_id": aid}
        _last_bootstrap_error = None


def set_bootstrap_error(message: str) -> None:
    global _last_bootstrap_error
    with _lock:
        _last_bootstrap_error = message.strip() or None


def get_last_bootstrap_error() -> str | None:
    with _lock:
        return _last_bootstrap_error


def get_retell_agent_id() -> str:
    configured = get_settings().retell_agent_id.strip()
    if configured:
        return configured
    with _lock:
        return _bootstrapped_agent_id or ""


def get_last_bootstrap_info() -> dict | None:
    with _lock:
        return dict(_last_bootstrap) if _last_bootstrap else None


def set_native_staging_agent(agent_id: str, meta: dict | None = None) -> None:
    global _native_staging_agent_id, _last_native_staging
    aid = (agent_id or "").strip()
    if not aid:
        return
    with _lock:
        _native_staging_agent_id = aid
        _last_native_staging = meta or {"agent_id": aid}


def get_native_staging_agent_id() -> str:
    configured = get_settings().retell_native_staging_agent_id.strip()
    if configured:
        return configured
    with _lock:
        return _native_staging_agent_id or ""


def get_last_native_staging_info() -> dict | None:
    with _lock:
        return dict(_last_native_staging) if _last_native_staging else None
