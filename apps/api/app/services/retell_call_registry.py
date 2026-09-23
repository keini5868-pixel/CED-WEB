"""Registro temporal call_id → user_id / conversation_id para Custom LLM Retell."""

from __future__ import annotations

import threading
from typing import Any

_lock = threading.Lock()
_by_call: dict[str, str] = {}
_by_user: dict[str, str] = {}
_by_call_conv: dict[str, str] = {}


def bind_call_user(
    call_id: str,
    user_id: str,
    conversation_id: str | None = None,
) -> None:
    cid = (call_id or "").strip()
    uid = (user_id or "").strip()
    conv = (conversation_id or "").strip()
    if not cid or not uid:
        return
    with _lock:
        _by_call[cid] = uid
        _by_user[uid] = cid
        if conv:
            _by_call_conv[cid] = conv


def _conversation_from_payload(payload: dict[str, Any] | None) -> str | None:
    if not payload:
        return None
    call = payload.get("call") if isinstance(payload.get("call"), dict) else {}
    bags = [
        call.get("metadata") if isinstance(call.get("metadata"), dict) else {},
        call.get("retell_llm_dynamic_variables")
        if isinstance(call.get("retell_llm_dynamic_variables"), dict)
        else {},
        payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
    ]
    for bag in bags:
        for key in ("conversation_id", "conversationId"):
            val = str(bag.get(key) or "").strip()
            if val:
                return val
    return None


def resolve_call_conversation(
    call_id: str,
    payload: dict[str, Any] | None = None,
) -> str | None:
    cid = (call_id or "").strip()
    conv = _conversation_from_payload(payload)
    if conv:
        if cid:
            with _lock:
                _by_call_conv[cid] = conv
        return conv
    if not cid:
        return None
    with _lock:
        return _by_call_conv.get(cid)


def resolve_call_user(call_id: str, payload: dict[str, Any] | None = None) -> str | None:
    cid = (call_id or "").strip()
    conv = _conversation_from_payload(payload)
    if payload:
        call = payload.get("call") or {}
        metadata = call.get("metadata") or {}
        for key in ("user_id", "userId"):
            val = metadata.get(key)
            if val:
                uid = str(val).strip()
                if uid:
                    bind_call_user(cid, uid, conversation_id=conv)
                    return uid
        retell_meta = call.get("retell_llm_dynamic_variables") or {}
        for key in ("user_id", "userId"):
            val = retell_meta.get(key)
            if val:
                uid = str(val).strip()
                if uid:
                    bind_call_user(cid, uid, conversation_id=conv)
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
        _by_call_conv.pop(cid, None)
        if uid and _by_user.get(uid) == cid:
            _by_user.pop(uid, None)
