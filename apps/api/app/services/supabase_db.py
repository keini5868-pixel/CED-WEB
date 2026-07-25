"""Acceso a Supabase (service role) para uso y conversaciones."""

from __future__ import annotations

import logging
import threading
from datetime import date, datetime, timezone
from typing import Any
from uuid import uuid4

from app.config import get_settings
from app.domain.plans import VOICE_COST_PER_MIN_USD

logger = logging.getLogger(__name__)

_VOICE_STREAM_COALESCE_SEC = 120


def _should_coalesce_voice_model_message(previous: str, incoming: str) -> str | None:
    """Decide si un parcial de voz debe actualizar, omitir o insertar nuevo."""
    prev = (previous or "").strip()
    new = (incoming or "").strip()
    if not prev or not new:
        return None
    if new.startswith(prev) and len(new) > len(prev):
        return "update"
    if prev.startswith(new) and len(prev) >= len(new):
        return "skip"
    return None


def _client():
    from app.services.supabase_client import get_supabase_admin

    return get_supabase_admin()


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


def create_conversation(
    user_id: str,
    title: str = "Conversación CED",
    *,
    channel: str = "voice",
) -> dict[str, Any]:
    from app.services.user_id_utils import normalize_user_id

    uid = normalize_user_id(user_id)
    # FK voice_conversations.user_id → profiles.id — sin perfil el insert falla
    # y la voz seguía sin conversation_id (historial vacío).
    ensure_profile(uid)
    client = _client()
    row = {
        "user_id": uid,
        "title": title,
        "channel": channel,
    }
    result = client.table("voice_conversations").insert(row).execute()
    conv = (result.data or [None])[0]
    if not conv or not conv.get("id"):
        logger.error(
            "[CONV] create_conversation sin id user=%s channel=%s data=%s",
            uid[:8],
            channel,
            result.data,
        )
        raise RuntimeError("No se pudo crear la conversación (sin id).")
    return conv


def get_conversation(conversation_id: str, user_id: str) -> dict[str, Any] | None:
    client = _client()
    result = (
        client.table("voice_conversations")
        .select("id, title, channel, created_at, updated_at")
        .eq("id", conversation_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    rows = result.data or []
    return rows[0] if rows else None


def append_message(
    conversation_id: str,
    user_id: str,
    role: str,
    content: str,
    *,
    session_id: str | None = None,
    channel: str = "voice",
) -> None:
    content = (content or "").strip()
    if not content:
        return
    client = _client()
    owner = (
        client.table("voice_conversations")
        .select("id, channel")
        .eq("id", conversation_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if not owner.data:
        raise PermissionError("Conversación no encontrada")
    conv_channel = str((owner.data[0] or {}).get("channel") or channel)

    if conv_channel == "voice" and role in ("model", "assistant", "user"):
        last = (
            client.table("voice_messages")
            .select("id, content, role, created_at")
            .eq("conversation_id", conversation_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if last.data:
            row = last.data[0] or {}
            if str(row.get("role") or "") in ("model", "assistant", "user"):
                prev = str(row.get("content") or "").strip()
                created_raw = row.get("created_at")
                recent = True
                if created_raw:
                    try:
                        created_at = datetime.fromisoformat(
                            str(created_raw).replace("Z", "+00:00")
                        )
                        recent = (
                            datetime.now(timezone.utc) - created_at
                        ).total_seconds() <= _VOICE_STREAM_COALESCE_SEC
                    except ValueError:
                        recent = True
                if recent and prev:
                    action = _should_coalesce_voice_model_message(prev, content)
                    if action == "update":
                        client.table("voice_messages").update(
                            {"content": content}
                        ).eq("id", row["id"]).execute()
                        client.table("voice_conversations").update(
                            {"updated_at": datetime.now(timezone.utc).isoformat()}
                        ).eq("id", conversation_id).execute()
                        return
                    if action == "skip":
                        return

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
    try:
        from app.services.conversation_memory import save_message as persist_message

        def _mirror() -> None:
            persist_message(
                user_id=user_id,
                session_id=session_id or conversation_id,
                channel=conv_channel if conv_channel in ("voice", "text") else channel,
                role=role,
                content=content,
                metadata={"conversation_id": conversation_id},
            )

        threading.Thread(target=_mirror, daemon=True).start()
    except Exception:  # noqa: BLE001
        pass


def list_conversations(
    user_id: str,
    limit: int = 30,
    *,
    channel: str | None = None,
) -> list[dict[str, Any]]:
    client = _client()
    q = (
        client.table("voice_conversations")
        .select("id, title, channel, created_at, updated_at")
        .eq("user_id", user_id)
    )
    if channel:
        q = q.eq("channel", channel)
    result = q.order("updated_at", desc=True).limit(limit).execute()
    return result.data or []


def list_conversations_filtered(
    user_id: str,
    *,
    limit: int = 50,
    channel: str | None = None,
    q: str | None = None,
) -> list[dict[str, Any]]:
    """Lista conversaciones con vista previa; filtra por canal y texto."""
    import re

    cap = max(1, min(limit, 100))
    rows = list_conversations(user_id, limit=cap * 2 if q else cap, channel=channel)
    needle = re.sub(r"[%_\\]", "", (q or "").strip().lower())
    out: list[dict[str, Any]] = []

    for conv in rows:
        msgs = get_conversation_messages(str(conv["id"]), user_id, limit=8)
        preview = ""
        for m in msgs:
            content = str(m.get("content") or "").strip()
            if content:
                preview = content[:160]
                break
        item = {**conv, "preview": preview, "message_count": len(msgs)}
        if needle:
            haystack = f"{conv.get('title', '')} {preview}".lower()
            if needle not in haystack:
                continue
        out.append(item)
        if len(out) >= cap:
            break
    return out


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






def list_hud_reminders(user_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
    try:
        client = _client()
        result = (
            client.table("hud_reminders")
            .select("id, text, reminder_date, reminder_time, created_at")
            .eq("user_id", user_id)
            .order("reminder_date")
            .order("reminder_time")
            .limit(limit)
            .execute()
        )
        return result.data or []
    except Exception:  # noqa: BLE001
        return []


def insert_hud_reminder(
    user_id: str,
    *,
    text: str,
    reminder_date: str,
    reminder_time: str = "09:00",
) -> dict[str, Any] | None:
    try:
        client = _client()
        row = {
            "user_id": user_id,
            "text": text[:500],
            "reminder_date": reminder_date,
            "reminder_time": reminder_time or "09:00",
        }
        result = client.table("hud_reminders").insert(row).execute()
        rows = result.data or []
        return rows[0] if rows else row
    except Exception:  # noqa: BLE001
        return None


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



def ensure_profile(user_id: str) -> None:
    """Garantiza fila en profiles antes de inserts dependientes."""
    from app.services.user_id_utils import normalize_user_id

    uid = normalize_user_id(user_id)
    existing = get_profile(uid)
    if existing:
        return
    logger.info("[DB] creating profile user_id=%s", uid)
    try:
        client = _client()
        auth_res = client.auth.admin.get_user_by_id(uid)
        user = auth_res.user if hasattr(auth_res, "user") else auth_res
        email = getattr(user, "email", None) or ""
        meta = getattr(user, "user_metadata", None) or {}
        full_name = meta.get("full_name", "") if isinstance(meta, dict) else ""
        client.table("profiles").upsert(
            {
                "id": uid,
                "email": email,
                "full_name": full_name or "",
                "role": "client",
            },
            on_conflict="id",
        ).execute()
    except Exception as exc:  # noqa: BLE001
        logger.error("[DB] profile ensure failed user=%s: %s", uid[:8], exc)
        raise ValueError("No se pudo crear perfil.") from exc
    if not get_profile(uid):
        raise ValueError("Perfil ausente tras ensure.")


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
    from app.domain.plans import plan_minutes_daily, normalize_plan_id

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
        if rows and rows[0].get("minutes_daily") is not None:
            return int(rows[0]["minutes_daily"])
    except Exception:  # noqa: BLE001
        pass
    sub = get_subscription(user_id)
    return plan_minutes_daily(normalize_plan_id((sub or {}).get("plan_id")))


def get_recharge_balance_usd(user_id: str) -> float:
    try:
        client = _client()
        result = (
            client.table("recharge_balances")
            .select("balance_usd")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        if rows and rows[0].get("balance_usd") is not None:
            return float(rows[0]["balance_usd"])
    except Exception:  # noqa: BLE001
        pass
    return 0.0


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


def stripe_event_processed(event_id: str) -> bool:
    if not event_id:
        return False
    try:
        client = _client()
        result = (
            client.table("transactions")
            .select("id")
            .eq("stripe_event_id", event_id)
            .limit(1)
            .execute()
        )
        return bool(result.data)
    except Exception:  # noqa: BLE001
        return False


def record_transaction(
    *,
    user_id: str,
    tx_type: str,
    amount_usd: float,
    stripe_event_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    try:
        client = _client()
        client.table("transactions").insert(
            {
                "user_id": user_id,
                "type": tx_type,
                "amount_usd": round(amount_usd, 2),
                "stripe_event_id": stripe_event_id,
                "metadata": metadata or {},
            }
        ).execute()
    except Exception:  # noqa: BLE001
        logger.exception("[DB] record_transaction failed")


def get_user_id_by_stripe_customer(customer_id: str) -> str | None:
    try:
        client = _client()
        result = (
            client.table("subscriptions")
            .select("user_id")
            .eq("stripe_customer_id", customer_id)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        return str(rows[0]["user_id"]) if rows else None
    except Exception:  # noqa: BLE001
        return None


def update_subscription_stripe_customer(user_id: str, customer_id: str) -> None:
    try:
        client = _client()
        result = (
            client.table("subscriptions")
            .update(
                {
                    "stripe_customer_id": customer_id,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            .eq("user_id", user_id)
            .execute()
        )
        if not result.data:
            client.table("subscriptions").upsert(
                {
                    "user_id": user_id,
                    "plan_id": "free_basic",
                    "status": "active",
                    "stripe_customer_id": customer_id,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
                on_conflict="user_id",
            ).execute()
    except Exception:  # noqa: BLE001
        pass


def upsert_paid_subscription(
    *,
    user_id: str,
    plan_id: str,
    status: str,
    stripe_subscription_id: str | None = None,
    stripe_customer_id: str | None = None,
    current_period_end: str | None = None,
    price_locked_for_life: bool = False,
    minutes_daily: int | None = None,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    row: dict[str, Any] = {
        "user_id": user_id,
        "plan_id": plan_id,
        "status": status,
        "access_type": "paid",
        "trial_ends_at": None,
        "updated_at": now,
        "price_locked_for_life": price_locked_for_life,
    }
    if stripe_subscription_id:
        row["stripe_subscription_id"] = stripe_subscription_id
    if stripe_customer_id:
        row["stripe_customer_id"] = stripe_customer_id
    if current_period_end:
        row["current_period_end"] = current_period_end
    try:
        client = _client()
        client.table("subscriptions").upsert(row, on_conflict="user_id").execute()
        if minutes_daily is not None:
            client.table("usage_limits").upsert(
                {
                    "user_id": user_id,
                    "minutes_daily": minutes_daily,
                    "updated_at": now,
                },
                on_conflict="user_id",
            ).execute()
    except Exception:  # noqa: BLE001
        logger.exception("[DB] upsert_paid_subscription failed user=%s", user_id)


def update_subscription_status(user_id: str, status: str) -> None:
    try:
        client = _client()
        client.table("subscriptions").update(
            {
                "status": status,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("user_id", user_id).execute()
    except Exception:  # noqa: BLE001
        pass


def downgrade_to_free_basic(user_id: str) -> None:
    from app.domain.plans import PlanId, plan_minutes_daily

    now = datetime.now(timezone.utc).isoformat()
    try:
        client = _client()
        client.table("subscriptions").upsert(
            {
                "user_id": user_id,
                "plan_id": PlanId.FREE_BASIC.value,
                "status": "active",
                "access_type": "paid",
                "stripe_subscription_id": None,
                "trial_ends_at": None,
                "updated_at": now,
            },
            on_conflict="user_id",
        ).execute()
        client.table("usage_limits").upsert(
            {
                "user_id": user_id,
                "minutes_daily": plan_minutes_daily(PlanId.FREE_BASIC.value),
                "updated_at": now,
            },
            on_conflict="user_id",
        ).execute()
    except Exception:  # noqa: BLE001
        logger.exception("[DB] downgrade_to_free_basic failed")


def expire_trial_if_needed(user_id: str) -> bool:
    """Retorna True si el trial ya expiró (sin auto-downgrade)."""
    sub = get_subscription(user_id)
    if not sub or str(sub.get("status")) != "trialing":
        return False
    trial_end = sub.get("trial_ends_at")
    if not trial_end:
        return False
    try:
        end = datetime.fromisoformat(str(trial_end).replace("Z", "+00:00"))
    except ValueError:
        return False
    return end <= datetime.now(timezone.utc)


def credit_recharge_balance(
    user_id: str,
    *,
    amount_paid_usd: float,
    client_balance_usd: float,
    margin_keini_usd: float,
    stripe_payment_intent_id: str | None = None,
    stripe_event_id: str | None = None,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    try:
        client = _client()
        current = get_recharge_balance_usd(user_id)
        new_balance = round(current + client_balance_usd, 2)
        client.table("recharge_balances").upsert(
            {"user_id": user_id, "balance_usd": new_balance, "updated_at": now},
            on_conflict="user_id",
        ).execute()
        client.table("recharges").insert(
            {
                "user_id": user_id,
                "amount_paid_usd": round(amount_paid_usd, 2),
                "client_balance_usd": round(client_balance_usd, 2),
                "margin_keini_usd": round(margin_keini_usd, 2),
                "estimated_hours": round(
                    client_balance_usd / max(VOICE_COST_PER_MIN_USD * 60.0, 0.01), 2
                )
                if client_balance_usd
                else 0,

                "stripe_payment_intent_id": stripe_payment_intent_id,
            }
        ).execute()
        record_transaction(
            user_id=user_id,
            tx_type="recharge",
            amount_usd=amount_paid_usd,
            stripe_event_id=stripe_event_id,
            metadata={"client_balance_usd": client_balance_usd},
        )
    except Exception:  # noqa: BLE001
        logger.exception("[DB] credit_recharge_balance failed")


def debit_recharge_balance(
    user_id: str,
    amount_usd: float,
    *,
    resource: str | None = None,
    units: float | None = None,
) -> bool:
    """Debita monedero. Devuelve False si no hay saldo suficiente o falla DB."""
    try:
        amount = round(float(amount_usd), 4)
        if amount <= 0:
            return True
        client = _client()
        current = get_recharge_balance_usd(user_id)
        if current + 1e-9 < amount:
            return False
        new_balance = max(0.0, round(current - amount, 2))
        client.table("recharge_balances").upsert(
            {
                "user_id": user_id,
                "balance_usd": new_balance,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            on_conflict="user_id",
        ).execute()
        logger.info(
            "[DB] wallet debit user=%s amount=%.4f resource=%s units=%s bal=%.2f",
            user_id[:8],
            amount,
            resource,
            units,
            new_balance,
        )
        return True
    except Exception:  # noqa: BLE001
        logger.exception("[DB] debit_recharge_balance failed")
        return False


def get_founding_slots() -> tuple[int, int]:
    try:
        client = _client()
        result = client.table("founding_registry").select("slots_used, slots_max").eq("id", 1).execute()
        row = (result.data or [{}])[0]
        return int(row.get("slots_used") or 0), int(row.get("slots_max") or 50)
    except Exception:  # noqa: BLE001
        return 0, 50


def claim_founding_slot(user_id: str) -> None:
    try:
        client = _client()
        used, cap = get_founding_slots()
        if used >= cap:
            return
        client.table("founding_registry").update(
            {
                "slots_used": used + 1,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("id", 1).execute()
        mark_founding_profile(user_id, 149)
    except Exception:  # noqa: BLE001
        logger.exception("[DB] claim_founding_slot failed")


def mark_founding_profile(user_id: str, price_locked_usd: int) -> None:
    try:
        client = _client()
        used, _ = get_founding_slots()
        client.table("profiles").update(
            {
                "is_founding_member": True,
                "founding_slot_number": used,
                "price_locked_usd": price_locked_usd,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("id", user_id).execute()
    except Exception:  # noqa: BLE001
        pass


def save_pdf_artifact(
    *,
    file_id: str,
    user_id: str,
    title: str,
    filename: str,
    pdf_bytes: bytes,
    conversation_id: str | None = None,
) -> bool:
    import base64

    from app.services.supabase_client import service_role_configured

    if not service_role_configured():
        logger.error(
            "[DB] save_pdf_artifact skipped — SUPABASE_SERVICE_ROLE_KEY required (RLS deny-all)"
        )
        return False

    from app.services.user_id_utils import normalize_user_id

    uid = normalize_user_id(user_id)
    try:
        from app.services.supabase_client import get_supabase_admin

        client = get_supabase_admin(require_service_role=True)
        row: dict[str, Any] = {
            "file_id": file_id,
            "user_id": uid,
            "title": title,
            "filename": filename,
            "pdf_base64": base64.b64encode(pdf_bytes).decode("ascii"),
        }
        if conversation_id:
            row["conversation_id"] = conversation_id
        client.table("ced_pdf_artifacts").upsert(row).execute()
        return True
    except Exception:  # noqa: BLE001
        logger.exception("[DB] save_pdf_artifact failed file_id=%s", file_id)
        return False


def get_pdf_artifact(file_id: str, user_id: str) -> tuple[bytes, str, str] | None:
    import base64

    from app.services.user_id_utils import normalize_user_id

    uid = normalize_user_id(user_id)
    try:
        from app.services.supabase_client import get_supabase_admin, service_role_configured

        if not service_role_configured():
            return None
        client = get_supabase_admin(require_service_role=True)
        result = (
            client.table("ced_pdf_artifacts")
            .select("filename, title, pdf_base64")
            .eq("file_id", file_id)
            .eq("user_id", uid)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        if not rows:
            return None
        row = rows[0]
        raw = base64.b64decode(str(row.get("pdf_base64") or ""))
        if not raw:
            return None
        return raw, str(row.get("filename") or "documento.pdf"), str(row.get("title") or "Documento")
    except Exception:  # noqa: BLE001
        logger.exception("[DB] get_pdf_artifact failed file_id=%s", file_id)
        return None


def list_pdf_artifacts(user_id: str, *, limit: int = 40) -> list[dict[str, Any]]:
    try:
        client = _client()
        result = (
            client.table("ced_pdf_artifacts")
            .select("file_id, title, filename, conversation_id, created_at")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data or []
    except Exception:  # noqa: BLE001
        logger.warning("[DB] list_pdf_artifacts failed — tabla puede no existir aún")
        return []


def count_pdfs_today(user_id: str) -> int:
    """Cuenta PDFs generados hoy (UTC) — usado para el tope diario gratis de Básico."""
    try:
        client = _client()
        start = today_utc().isoformat()
        result = (
            client.table("ced_pdf_artifacts")
            .select("file_id")
            .eq("user_id", user_id)
            .gte("created_at", start)
            .execute()
        )
        return len(result.data or [])
    except Exception:  # noqa: BLE001
        return 0


def count_generated_images_today(user_id: str) -> tuple[int, int, int]:
    """Cuenta imágenes standard, HD y con texto (Ideogram) del día actual (UTC)."""
    try:
        client = _client()
        start = today_utc().isoformat()
        result = (
            client.table("generated_images")
            .select("quality")
            .eq("user_id", user_id)
            .gte("created_at", start)
            .execute()
        )
        rows = result.data or []
        text_n = sum(1 for r in rows if (r.get("quality") or "") == "text")
        hd = sum(1 for r in rows if (r.get("quality") or "") == "hd")
        std = len(rows) - text_n - hd
        return std, hd, text_n
    except Exception:  # noqa: BLE001
        return 0, 0, 0


def count_generated_images_this_month(user_id: str) -> tuple[int, int, int]:
    """Cuenta imágenes standard, HD y con texto (Ideogram) del mes actual."""
    try:
        client = _client()
        start = today_utc().replace(day=1).isoformat()
        result = (
            client.table("generated_images")
            .select("quality")
            .eq("user_id", user_id)
            .gte("created_at", start)
            .execute()
        )
        rows = result.data or []
        text_n = sum(1 for r in rows if (r.get("quality") or "") == "text")
        hd = sum(1 for r in rows if (r.get("quality") or "") == "hd")
        std = len(rows) - text_n - hd
        return std, hd, text_n
    except Exception:  # noqa: BLE001
        return 0, 0, 0


def insert_generated_image(
    *,
    user_id: str,
    prompt: str,
    quality: str,
    model: str,
    public_url: str,
    estimated_cost_usd: float,
) -> None:
    client = _client()
    client.table("generated_images").insert(
        {
            "user_id": user_id,
            "prompt": prompt[:4000],
            "quality": quality,
            "model": model,
            "public_url": public_url[:8000] if public_url else None,
            "estimated_cost_usd": estimated_cost_usd,
        }
    ).execute()

