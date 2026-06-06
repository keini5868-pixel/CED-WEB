"""Acceso a Supabase (service role) para uso y conversaciones."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from uuid import uuid4

from app.config import get_settings


def _client():
    from supabase import create_client

    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise RuntimeError("Supabase no configurado")
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


def today_utc() -> date:
    return datetime.now(timezone.utc).date()


def get_usage_minutes_today(user_id: str) -> float:
    client = _client()
    today = today_utc().isoformat()
    result = (
        client.table("usage_logs")
        .select("minutes_consumed")
        .eq("user_id", user_id)
        .eq("usage_date", today)
        .execute()
    )
    rows = result.data or []
    return float(sum(float(r.get("minutes_consumed") or 0) for r in rows))


def reset_usage_minutes_today(user_id: str) -> float:
    """Elimina el uso de voz de hoy. Devuelve minutos que tenía antes."""
    before = get_usage_minutes_today(user_id)
    client = _client()
    today = today_utc().isoformat()
    client.table("usage_logs").delete().eq("user_id", user_id).eq(
        "usage_date", today
    ).execute()
    return before


def add_usage_minutes(
    user_id: str,
    minutes: float,
    session_id: str | None = None,
) -> float:
    if minutes <= 0:
        return get_usage_minutes_today(user_id)
    client = _client()
    today = today_utc().isoformat()
    sid = session_id or str(uuid4())

    if session_id:
        existing = (
            client.table("usage_logs")
            .select("id, minutes_consumed")
            .eq("user_id", user_id)
            .eq("usage_date", today)
            .eq("session_id", sid)
            .limit(1)
            .execute()
        )
        rows = existing.data or []
        if rows:
            row = rows[0]
            total = round(float(row.get("minutes_consumed") or 0) + minutes, 4)
            client.table("usage_logs").update({"minutes_consumed": total}).eq(
                "id", row["id"]
            ).execute()
            return get_usage_minutes_today(user_id)

    client.table("usage_logs").insert(
        {
            "user_id": user_id,
            "usage_date": today,
            "minutes_consumed": round(minutes, 4),
            "source": "gemini_live",
            "session_id": sid,
        }
    ).execute()
    return get_usage_minutes_today(user_id)


def create_conversation(user_id: str, title: str = "Conversación CED") -> dict[str, Any]:
    client = _client()
    row = {
        "user_id": user_id,
        "title": title,
    }
    result = client.table("voice_conversations").insert(row).execute()
    return (result.data or [{}])[0]


def append_message(
    conversation_id: str,
    user_id: str,
    role: str,
    content: str,
) -> None:
    if not content.strip():
        return
    client = _client()
    owner = (
        client.table("voice_conversations")
        .select("id")
        .eq("id", conversation_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if not owner.data:
        raise PermissionError("Conversación no encontrada")
    client.table("voice_messages").insert(
        {
            "conversation_id": conversation_id,
            "role": role,
            "content": content.strip(),
        }
    ).execute()
    client.table("voice_conversations").update(
        {"updated_at": datetime.now(timezone.utc).isoformat()}
    ).eq("id", conversation_id).execute()


def list_conversations(user_id: str, limit: int = 30) -> list[dict[str, Any]]:
    client = _client()
    result = (
        client.table("voice_conversations")
        .select("id, title, created_at, updated_at")
        .eq("user_id", user_id)
        .order("updated_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


def get_conversation_messages(
    conversation_id: str,
    user_id: str,
    limit: int = 100,
) -> list[dict[str, Any]]:
    client = _client()
    conv = (
        client.table("voice_conversations")
        .select("id")
        .eq("id", conversation_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if not conv.data:
        return []
    result = (
        client.table("voice_messages")
        .select("id, role, content, created_at")
        .eq("conversation_id", conversation_id)
        .order("created_at")
        .limit(limit)
        .execute()
    )
    return result.data or []


def list_recent_voice_activity(user_id: str, limit: int = 3) -> list[str]:
    """Últimos mensajes de voz para tarjeta ACTIVIDAD CED."""
    try:
        convs = list_conversations(user_id, limit=1)
        if not convs:
            return []
        msgs = get_conversation_messages(convs[0]["id"], user_id, limit=40)
        if not msgs:
            return []
        lines: list[str] = []
        seen: set[str] = set()
        for msg in msgs[-limit * 2:]:
            role = "Tú" if msg.get("role") == "user" else "CED"
            content = str(msg.get("content") or "").strip()
            if not content:
                continue
            line = f"{role}: {content[:58]}"
            if line in seen:
                continue
            seen.add(line)
            lines.append(line)
            if len(lines) >= limit:
                break
        return lines
    except Exception:  # noqa: BLE001
        return []


def log_ced_activity(
    user_id: str,
    action: str,
    detail: str | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    client = _client()
    client.table("ced_activity_logs").insert(
        {
            "user_id": user_id,
            "action": action,
            "detail": detail,
            "meta": meta or {},
        }
    ).execute()


def list_recent_ced_activity(user_id: str, limit: int = 5) -> list[str]:
    try:
        client = _client()
        result = (
            client.table("ced_activity_logs")
            .select("action, detail, created_at")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        lines: list[str] = []
        for row in result.data or []:
            action = str(row.get("action") or "actividad")
            detail = str(row.get("detail") or "").strip()
            label = action.replace("_", " ").upper()
            lines.append(f"{label}: {detail[:52]}" if detail else label)
        return lines
    except Exception:  # noqa: BLE001
        return []


def list_activity_lines(user_id: str, limit: int = 3) -> list[str]:
    logs = list_recent_ced_activity(user_id, limit=limit)
    if logs:
        return logs[:limit]
    return list_recent_voice_activity(user_id, limit=limit)


def get_meta_connection(user_id: str) -> dict[str, Any] | None:
    try:
        client = _client()
        result = (
            client.table("meta_connections")
            .select("*")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        return rows[0] if rows else None
    except Exception:  # noqa: BLE001
        return None


def upsert_meta_connection(user_id: str, data: dict[str, Any]) -> dict[str, Any]:
    client = _client()
    row = {"user_id": user_id, **data, "updated_at": datetime.now(timezone.utc).isoformat()}
    result = client.table("meta_connections").upsert(row, on_conflict="user_id").execute()
    return (result.data or [row])[0]


def list_leads_today(user_id: str, limit: int = 5) -> list[dict[str, Any]]:
    try:
        client = _client()
        start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        result = (
            client.table("detected_leads")
            .select("handle, score, is_hot, intent, detected_at")
            .eq("user_id", user_id)
            .gte("detected_at", start.isoformat())
            .order("detected_at", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data or []
    except Exception:  # noqa: BLE001
        return []


def count_leads_today(user_id: str) -> int:
    return len(list_leads_today(user_id, limit=100))


def get_profile(user_id: str) -> dict[str, Any] | None:
    try:
        client = _client()
        result = (
            client.table("profiles")
            .select("*")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        return rows[0] if rows else None
    except Exception:  # noqa: BLE001
        return None


def get_usage_minutes_week(user_id: str) -> float:
    try:
        client = _client()
        week_ago = (datetime.now(timezone.utc).date()).isoformat()
        result = (
            client.table("usage_logs")
            .select("minutes_consumed, usage_date")
            .eq("user_id", user_id)
            .execute()
        )
        total = 0.0
        for row in result.data or []:
            total += float(row.get("minutes_consumed") or 0)
        return total
    except Exception:  # noqa: BLE001
        return 0.0


def get_subscription(user_id: str) -> dict[str, Any] | None:
    try:
        client = _client()
        result = (
            client.table("subscriptions")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        return rows[0] if rows else None
    except Exception:  # noqa: BLE001
        return None


def get_usage_limit_minutes(user_id: str) -> int:
    from app.domain.plans import CED_ELITE

    try:
        client = _client()
        result = (
            client.table("usage_limits")
            .select("minutes_daily")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        if rows and rows[0].get("minutes_daily"):
            return int(rows[0]["minutes_daily"])
    except Exception:  # noqa: BLE001
        pass
    return CED_ELITE.gemini_minutes_per_day


def log_admin_audit(
    admin_user_id: str,
    action: str,
    *,
    target_user_id: str | None = None,
    payload: dict[str, Any] | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    try:
        client = _client()
        client.table("admin_audit_logs").insert(
            {
                "admin_user_id": admin_user_id,
                "action": action,
                "target_user_id": target_user_id,
                "payload": payload or {},
                "ip_address": ip_address,
                "user_agent": user_agent,
            }
        ).execute()
    except Exception:  # noqa: BLE001
        pass
