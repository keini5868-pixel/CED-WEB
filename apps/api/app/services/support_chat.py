"""Chat de soporte — conversaciones y mensajes."""

from __future__ import annotations

import html
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from fastapi import HTTPException

from app.deps.auth import is_super_admin
from app.services.supabase_db import _client

logger = logging.getLogger(__name__)

VALID_CATEGORIES = frozenset({"bug", "idea", "question", "other"})
VALID_STATUSES = frozenset({"open", "in_progress", "resolved"})
USER_MESSAGE_LIMIT_PER_MIN = 10


def _sanitize_content(text: str) -> str:
    cleaned = html.escape((text or "").strip())
    return cleaned[:8000]


def _parse_uuid(value: str, label: str = "id") -> str:
    try:
        return str(UUID(value.strip()))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{label} inválido") from exc


def _conversation_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "category": row["category"],
        "status": row["status"],
        "last_message_at": row.get("last_message_at"),
        "unread_by_admin": bool(row.get("unread_by_admin")),
        "unread_by_user": bool(row.get("unread_by_user")),
        "created_at": row.get("created_at"),
    }


def _message_row(row: dict[str, Any]) -> dict[str, Any]:
    attachments = row.get("attachments") or []
    if not isinstance(attachments, list):
        attachments = []
    return {
        "id": row["id"],
        "conversation_id": row["conversation_id"],
        "sender_type": row["sender_type"],
        "sender_id": row["sender_id"],
        "content": row.get("content") or "",
        "attachments": attachments,
        "created_at": row.get("created_at"),
    }


def _get_profile_map(user_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not user_ids:
        return {}
    client = _client()
    result = (
        client.table("profiles")
        .select("id, email, full_name")
        .in_("id", list(set(user_ids)))
        .execute()
    )
    return {str(r["id"]): r for r in (result.data or [])}


def _assert_user_message_rate(user_id: str) -> None:
    client = _client()
    since = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    result = (
        client.table("support_messages")
        .select("id")
        .eq("sender_id", user_id)
        .eq("sender_type", "user")
        .gte("created_at", since)
        .execute()
    )
    if len(result.data or []) >= USER_MESSAGE_LIMIT_PER_MIN:
        raise HTTPException(status_code=429, detail="Demasiados mensajes. Espera un momento.")


def get_conversation(conversation_id: str) -> dict[str, Any] | None:
    client = _client()
    result = (
        client.table("support_conversations")
        .select("*")
        .eq("id", conversation_id)
        .limit(1)
        .execute()
    )
    rows = result.data or []
    return rows[0] if rows else None


def assert_conversation_access(
    conversation_id: str,
    *,
    user_id: str,
    email: str | None,
    role: str | None,
    admin: bool = False,
) -> dict[str, Any]:
    conv = get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    is_admin = admin or is_super_admin(email, role)
    if not is_admin and str(conv["user_id"]) != user_id:
        raise HTTPException(status_code=403, detail="Sin acceso a esta conversación")
    return conv


def create_conversation(user_id: str, category: str) -> dict[str, Any]:
    cat = (category or "").strip().lower()
    if cat not in VALID_CATEGORIES:
        raise HTTPException(status_code=400, detail="Categoría inválida")
    client = _client()
    row = {
        "user_id": user_id,
        "category": cat,
        "status": "open",
        "unread_by_admin": True,
        "unread_by_user": False,
    }
    result = client.table("support_conversations").insert(row).execute()
    return _conversation_row((result.data or [{}])[0])


def list_user_conversations(user_id: str) -> list[dict[str, Any]]:
    client = _client()
    result = (
        client.table("support_conversations")
        .select("*")
        .eq("user_id", user_id)
        .order("last_message_at", desc=True)
        .execute()
    )
    return [_conversation_row(r) for r in (result.data or [])]


def list_admin_conversations(
    *,
    status: str | None = None,
    category: str | None = None,
    unread_only: bool = False,
) -> list[dict[str, Any]]:
    client = _client()
    query = client.table("support_conversations").select("*")
    if status and status in VALID_STATUSES:
        query = query.eq("status", status)
    if category and category in VALID_CATEGORIES:
        query = query.eq("category", category)
    if unread_only:
        query = query.eq("unread_by_admin", True)
    result = query.order("last_message_at", desc=True).execute()
    rows = result.data or []
    profiles = _get_profile_map([str(r["user_id"]) for r in rows])
    out: list[dict[str, Any]] = []
    for row in rows:
        item = _conversation_row(row)
        prof = profiles.get(str(row["user_id"]), {})
        item["user_email"] = prof.get("email") or ""
        item["user_name"] = prof.get("full_name") or prof.get("email") or "Usuario"
        preview = get_last_message_preview(str(row["id"]))
        item["last_message_preview"] = preview
        out.append(item)
    return out


def get_last_message_preview(conversation_id: str) -> str:
    client = _client()
    result = (
        client.table("support_messages")
        .select("content")
        .eq("conversation_id", conversation_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = result.data or []
    if not rows:
        return ""
    text = str(rows[0].get("content") or "")
    return text[:120]


def list_messages(conversation_id: str) -> list[dict[str, Any]]:
    client = _client()
    result = (
        client.table("support_messages")
        .select("*")
        .eq("conversation_id", conversation_id)
        .order("created_at", desc=False)
        .execute()
    )
    return [_message_row(r) for r in (result.data or [])]


def add_message(
    conversation_id: str,
    *,
    sender_id: str,
    sender_type: str,
    content: str,
    attachments: list[str] | None = None,
) -> dict[str, Any]:
    if sender_type not in ("user", "admin"):
        raise HTTPException(status_code=400, detail="sender_type inválido")
    if sender_type == "user":
        _assert_user_message_rate(sender_id)
    body = _sanitize_content(content)
    att = [a for a in (attachments or []) if isinstance(a, str) and a.strip()]
    if not body and not att:
        raise HTTPException(status_code=400, detail="Mensaje vacío")
    client = _client()
    msg_row = {
        "conversation_id": conversation_id,
        "sender_type": sender_type,
        "sender_id": sender_id,
        "content": body,
        "attachments": att,
    }
    result = client.table("support_messages").insert(msg_row).execute()
    message = _message_row((result.data or [{}])[0])
    now = datetime.now(timezone.utc).isoformat()
    patch: dict[str, Any] = {"last_message_at": now}
    conv = get_conversation(conversation_id)
    if sender_type == "user":
        patch["unread_by_admin"] = True
        patch["unread_by_user"] = False
        if conv and conv.get("status") == "resolved":
            patch["status"] = "open"
    else:
        patch["unread_by_user"] = True
        patch["unread_by_admin"] = False
    client.table("support_conversations").update(patch).eq("id", conversation_id).execute()
    return message


def mark_read(conversation_id: str, *, reader: str) -> None:
    client = _client()
    patch: dict[str, Any] = {}
    if reader == "admin":
        patch["unread_by_admin"] = False
    elif reader == "user":
        patch["unread_by_user"] = False
    else:
        return
    client.table("support_conversations").update(patch).eq("id", conversation_id).execute()


def update_status(conversation_id: str, status: str) -> dict[str, Any]:
    st = (status or "").strip().lower()
    if st not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail="Estado inválido")
    client = _client()
    result = (
        client.table("support_conversations")
        .update({"status": st})
        .eq("id", conversation_id)
        .execute()
    )
    rows = result.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    return _conversation_row(rows[0])


def count_unread_for_user(user_id: str) -> int:
    client = _client()
    result = (
        client.table("support_conversations")
        .select("id")
        .eq("user_id", user_id)
        .eq("unread_by_user", True)
        .execute()
    )
    return len(result.data or [])


def count_unread_for_admin() -> int:
    client = _client()
    result = (
        client.table("support_conversations")
        .select("id")
        .eq("unread_by_admin", True)
        .execute()
    )
    return len(result.data or [])


def user_owns_attachment(user_id: str, file_name: str, *, admin: bool) -> bool:
    if admin:
        return True
    prefix = f"{user_id[:8]}_"
    return file_name.startswith(prefix)
