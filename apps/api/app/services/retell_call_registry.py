"""Registro temporal call_id → user_id para Custom LLM Retell."""

from __future__ import annotations

import threading
from typing import Any

_lock = threading.Lock()
_by_call: dict[str, str] = {}
_by_user: dict[str, str] = {}


def bind_call_user(call_id: str, user_id: str) -> None:
    cid = (call_id or "").strip()
    uid = (user_id or "").strip()
    if not cid or not uid:
        return
    with _lock:
        _by_call[cid] = uid
        _by_user[uid] = cid


def resolve_call_user(call_id: str, payload: dict[str, Any] | None = None) -> str | None:
    cid = (call_id or "").strip()
    if payload:
        call = payload.get("call") or {}
        metadata = call.get("metadata") or {}
        for key in ("user_id", "userId"):
            val = metadata.get(key)
            if val:
                uid = str(val).strip()
                if uid:
                    bind_call_user(cid, uid)
                    return uid
        retell_meta = call.get("retell_llm_dynamic_variables") or {}
        for key in ("user_id", "userId"):
            val = retell_meta.get(key)
            if val:
                uid = str(val).strip()
                if uid:
                    bind_call_user(cid, uid)
                    return uid

    with _lock:
        return _by_call.get(cid)


def resolve_user_active_call(user_id: str) -> str | None:
    uid = (user_id or "").strip()
    if not uid:
        return None
    with _lock:
        return _by_user.get(uid)


def release_call_user(call_id: str) -> None:
    cid = (call_id or "").strip()
    if not cid:
        return
    with _lock:
        uid = _by_call.pop(cid, None)
        if uid and _by_user.get(uid) == cid:
            _by_user.pop(uid, None)
