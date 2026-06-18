"""Agent ID Retell — env + caché en memoria tras bootstrap automático."""

from __future__ import annotations

import threading

from app.config import get_settings

_lock = threading.Lock()
_bootstrapped_agent_id: str | None = None
_last_bootstrap: dict | None = None


def set_bootstrapped_agent(agent_id: str, meta: dict | None = None) -> None:
    global _bootstrapped_agent_id, _last_bootstrap
    aid = (agent_id or "").strip()
    if not aid:
        return
    with _lock:
        _bootstrapped_agent_id = aid
        _last_bootstrap = meta or {"agent_id": aid}


def get_retell_agent_id() -> str:
    configured = get_settings().retell_agent_id.strip()
    if configured:
        return configured
    with _lock:
        return _bootstrapped_agent_id or ""


def get_last_bootstrap_info() -> dict | None:
    with _lock:
        return dict(_last_bootstrap) if _last_bootstrap else None
