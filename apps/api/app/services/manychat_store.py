"""Cuentas ManyChat por usuario CED — DB o memoria de proceso."""

from __future__ import annotations

import logging
import secrets
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from app.services.supabase_db import _client

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_DB_OK: bool | None = None
_ACCOUNTS: dict[str, dict[str, Any]] = {}
_CONTACTS: dict[tuple[str, str], dict[str, Any]] = {}
_MESSAGES: list[dict[str, Any]] = []

ROLES = ("closer", "qualifier", "support", "custom")
TONES = ("cercano", "formal", "directo")
CTA_WHEN = ("ready", "always", "never")


def reset_memory_for_tests() -> None:
    global _DB_OK
    with _LOCK:
        _ACCOUNTS.clear()
        _CONTACTS.clear()
        _MESSAGES.clear()
        _DB_OK = False


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | str | None) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return str(value or "")


def _use_db() -> bool:
    global _DB_OK
    if _DB_OK is not None:
        return _DB_OK
    try:
        _client().table("manychat_accounts").select("user_id").limit(1).execute()
        _DB_OK = True
    except Exception:
        logger.warning("ManyChat: tabla ausente, usando memoria de proceso.")
        _DB_OK = False
    return _DB_OK


def _new_secret() -> str:
    return secrets.token_hex(24)


def _blank_account(user_id: str) -> dict[str, Any]:
    now = _iso(_now())
    return {
        "user_id": user_id,
        "webhook_secret": _new_secret(),
        "enabled": False,
        "role": "closer",
        "tone": "cercano",
        "mission": "",
        "ask_lines": "",
        "objections": "",
        "never_say": "",
        "cta_when": "ready",
        "cta_url": "",
        "cta_label": "",
        "created_at": now,
        "updated_at": now,
    }


def _normalize_account(row: dict[str, Any], user_id: str) -> dict[str, Any]:
    role = str(row.get("role") or "closer").strip().lower()
    if role not in ROLES:
        role = "closer"
    tone = str(row.get("tone") or "cercano").strip().lower()
    if tone not in TONES:
        tone = "cercano"
    when = str(row.get("cta_when") or "ready").strip().lower()
    if when not in CTA_WHEN:
        when = "ready"
    return {
        "user_id": user_id,
        "webhook_secret": str(row.get("webhook_secret") or ""),
        "enabled": bool(row.get("enabled")),
        "role": role,
        "tone": tone,
        "mission": str(row.get("mission") or ""),
        "ask_lines": str(row.get("ask_lines") or ""),
        "objections": str(row.get("objections") or ""),
        "never_say": str(row.get("never_say") or ""),
        "cta_when": when,
        "cta_url": str(row.get("cta_url") or "").strip(),
        "cta_label": str(row.get("cta_label") or "").strip(),
        "created_at": _iso(row.get("created_at")),
        "updated_at": _iso(row.get("updated_at")),
    }


def get_account(user_id: str) -> dict[str, Any] | None:
    uid = (user_id or "").strip()
    if not uid:
        return None
    if _use_db():
        try:
            res = (
                _client()
                .table("manychat_accounts")
                .select("*")
                .eq("user_id", uid)
                .limit(1)
                .execute()
            )
            row = (res.data or [None])[0]
            return _normalize_account(row, uid) if row else None
        except Exception:
            logger.exception("[MANYCHAT] get_account failed")
            return None
    with _LOCK:
        row = _ACCOUNTS.get(uid)
        return _normalize_account(row, uid) if row else None


def get_account_by_secret(secret: str) -> dict[str, Any] | None:
    token = (secret or "").strip()
    if not token:
        return None
    if _use_db():
        try:
            res = (
                _client()
                .table("manychat_accounts")
                .select("*")
                .eq("webhook_secret", token)
                .limit(1)
                .execute()
            )
            row = (res.data or [None])[0]
            if not row:
                return None
            return _normalize_account(row, str(row.get("user_id") or ""))
        except Exception:
            logger.exception("[MANYCHAT] get_account_by_secret failed")
            return None
    with _LOCK:
        for uid, row in _ACCOUNTS.items():
            if str(row.get("webhook_secret") or "") == token:
                return _normalize_account(row, uid)
    return None


def ensure_account(user_id: str) -> dict[str, Any]:
    existing = get_account(user_id)
    if existing:
        return existing
    row = _blank_account(user_id)
    if _use_db():
        try:
            res = _client().table("manychat_accounts").upsert(row, on_conflict="user_id").execute()
            saved = (res.data or [row])[0]
            return _normalize_account(saved, user_id)
        except Exception:
            logger.exception("[MANYCHAT] ensure_account insert failed")
    with _LOCK:
        _ACCOUNTS[user_id] = dict(row)
    return _normalize_account(row, user_id)


def save_account(user_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    current = ensure_account(user_id)
    allowed = {
        "enabled",
        "role",
        "tone",
        "mission",
        "ask_lines",
        "objections",
        "never_say",
        "cta_when",
        "cta_url",
        "cta_label",
        "webhook_secret",
    }
    next_row = {**current}
    for key, value in patch.items():
        if key in allowed:
            next_row[key] = value
    next_row["updated_at"] = _iso(_now())
    next_row["user_id"] = user_id
    if _use_db():
        try:
            res = (
                _client()
                .table("manychat_accounts")
                .upsert(next_row, on_conflict="user_id")
                .execute()
            )
            saved = (res.data or [next_row])[0]
            return _normalize_account(saved, user_id)
        except Exception:
            logger.exception("[MANYCHAT] save_account failed")
    with _LOCK:
        _ACCOUNTS[user_id] = dict(next_row)
    return _normalize_account(next_row, user_id)


def rotate_secret(user_id: str) -> dict[str, Any]:
    return save_account(user_id, {"webhook_secret": _new_secret()})


def get_contact(user_id: str, subscriber_id: str) -> dict[str, Any] | None:
    sid = (subscriber_id or "").strip()
    if not sid:
        return None
    if _use_db():
        try:
            res = (
                _client()
                .table("manychat_contacts")
                .select("*")
                .eq("user_id", user_id)
                .eq("subscriber_id", sid)
                .limit(1)
                .execute()
            )
            return (res.data or [None])[0]
        except Exception:
            return None
    with _LOCK:
        return _CONTACTS.get((user_id, sid))


def upsert_contact(user_id: str, subscriber_id: str, data: dict[str, Any]) -> None:
    sid = (subscriber_id or "").strip() or "unknown"
    row = {
        "user_id": user_id,
        "subscriber_id": sid,
        "conversation_id": str(data.get("conversation_id") or ""),
        "display_name": str(data.get("display_name") or ""),
        "last_text": str(data.get("last_text") or "")[:500],
        "updated_at": _iso(_now()),
    }
    prev = get_contact(user_id, sid) or {}
    if not row["conversation_id"]:
        row["conversation_id"] = str(prev.get("conversation_id") or "")
    if not row["display_name"]:
        row["display_name"] = str(prev.get("display_name") or "")
    if _use_db():
        try:
            _client().table("manychat_contacts").upsert(
                row, on_conflict="user_id,subscriber_id"
            ).execute()
            return
        except Exception:
            logger.warning("[MANYCHAT] upsert_contact failed")
    with _LOCK:
        _CONTACTS[(user_id, sid)] = row


def log_message(user_id: str, subscriber_id: str, direction: str, body: str) -> None:
    row = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "subscriber_id": subscriber_id,
        "direction": direction,
        "body": (body or "")[:2000],
        "created_at": _iso(_now()),
    }
    if _use_db():
        try:
            _client().table("manychat_messages").insert(row).execute()
            return
        except Exception:
            logger.warning("[MANYCHAT] log_message skipped")
    with _LOCK:
        _MESSAGES.insert(0, row)
        del _MESSAGES[80:]


def list_messages(user_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
    if _use_db():
        try:
            res = (
                _client()
                .table("manychat_messages")
                .select("*")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            return list(res.data or [])
        except Exception:
            return []
    with _LOCK:
        return [m for m in _MESSAGES if m.get("user_id") == user_id][:limit]
