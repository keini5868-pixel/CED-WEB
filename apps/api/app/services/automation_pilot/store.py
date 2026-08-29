"""Persistencia Supabase — ced_automations / ced_leads / events."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.services import supabase_db

logger = logging.getLogger(__name__)


def _client():
    return supabase_db._client()


def list_automations(user_id: str) -> list[dict[str, Any]]:
    try:
        res = (
            _client()
            .table("ced_automations")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=False)
            .execute()
        )
        return list(res.data or [])
    except Exception:  # noqa: BLE001
        logger.exception("[AUTOMATION] list_automations failed")
        return []


def get_automation(user_id: str, automation_id: str) -> dict[str, Any] | None:
    try:
        res = (
            _client()
            .table("ced_automations")
            .select("*")
            .eq("user_id", user_id)
            .eq("id", automation_id)
            .limit(1)
            .execute()
        )
        rows = res.data or []
        return rows[0] if rows else None
    except Exception:  # noqa: BLE001
        logger.exception("[AUTOMATION] get_automation failed")
        return None


def upsert_automation(user_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    row = {
        **payload,
        "user_id": user_id,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        existing_id = str(payload.get("id") or "").strip()
        if existing_id:
            res = (
                _client()
                .table("ced_automations")
                .update(row)
                .eq("user_id", user_id)
                .eq("id", existing_id)
                .execute()
            )
        else:
            row.pop("id", None)
            res = _client().table("ced_automations").insert(row).execute()
        rows = res.data or []
        return rows[0] if rows else None
    except Exception:  # noqa: BLE001
        logger.exception("[AUTOMATION] upsert_automation failed")
        return None


def set_automation_status(user_id: str, automation_id: str, status: str) -> dict[str, Any] | None:
    return upsert_automation(
        user_id,
        {"id": automation_id, "status": status},
    )


def touch_triggered(automation_id: str) -> None:
    try:
        _client().table("ced_automations").update(
            {"last_triggered_at": datetime.now(timezone.utc).isoformat()}
        ).eq("id", automation_id).execute()
    except Exception:  # noqa: BLE001
        logger.warning("[AUTOMATION] touch_triggered failed id=%s", automation_id)


def list_active_for_channel(channel: str) -> list[dict[str, Any]]:
    try:
        res = (
            _client()
            .table("ced_automations")
            .select("*")
            .eq("channel", channel)
            .eq("status", "active")
            .execute()
        )
        return list(res.data or [])
    except Exception:  # noqa: BLE001
        logger.exception("[AUTOMATION] list_active_for_channel failed")
        return []


def count_active(user_id: str) -> int:
    try:
        res = (
            _client()
            .table("ced_automations")
            .select("id", count="exact")
            .eq("user_id", user_id)
            .eq("status", "active")
            .execute()
        )
        return int(res.count or 0)
    except Exception:  # noqa: BLE001
        return 0


def upsert_lead(
    user_id: str,
    *,
    contact_id: str,
    channel_origen: str,
    display_name: str | None = None,
    etiqueta: str | None = None,
    event: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    now = datetime.now(timezone.utc).isoformat()
    try:
        existing = (
            _client()
            .table("ced_leads")
            .select("*")
            .eq("user_id", user_id)
            .eq("contact_id", contact_id)
            .eq("channel_origen", channel_origen)
            .limit(1)
            .execute()
        )
        rows = existing.data or []
        historial = list((rows[0].get("historial") if rows else None) or [])
        if event:
            historial.append({**event, "at": now})
            historial = historial[-40:]
        payload: dict[str, Any] = {
            "user_id": user_id,
            "contact_id": contact_id,
            "channel_origen": channel_origen,
            "historial": historial,
            "last_contact_at": now,
            "updated_at": now,
        }
        if display_name:
            payload["display_name"] = display_name
        if etiqueta:
            payload["etiqueta"] = etiqueta
        if rows:
            res = (
                _client()
                .table("ced_leads")
                .update(payload)
                .eq("id", rows[0]["id"])
                .execute()
            )
        else:
            payload["etiqueta"] = etiqueta or "frio"
            res = _client().table("ced_leads").insert(payload).execute()
        out = res.data or []
        return out[0] if out else None
    except Exception:  # noqa: BLE001
        logger.exception("[AUTOMATION] upsert_lead failed")
        return None


def list_leads(user_id: str, *, limit: int = 40) -> list[dict[str, Any]]:
    try:
        res = (
            _client()
            .table("ced_leads")
            .select("*")
            .eq("user_id", user_id)
            .order("last_contact_at", desc=True)
            .limit(limit)
            .execute()
        )
        return list(res.data or [])
    except Exception:  # noqa: BLE001
        logger.exception("[AUTOMATION] list_leads failed")
        return []


def log_event(row: dict[str, Any]) -> None:
    try:
        _client().table("ced_automation_events").insert(row).execute()
    except Exception:  # noqa: BLE001
        logger.warning("[AUTOMATION] log_event failed type=%s", row.get("event_type"))


def narrative_stats(user_id: str) -> dict[str, int]:
    leads = list_leads(user_id, limit=200)
    ig = sum(1 for L in leads if L.get("channel_origen") == "instagram")
    fb = sum(1 for L in leads if L.get("channel_origen") == "facebook")
    wa = sum(1 for L in leads if L.get("channel_origen") == "whatsapp")
    hot = sum(1 for L in leads if L.get("etiqueta") == "caliente")
    return {
        "instagram_contacts": ig,
        "facebook_contacts": fb,
        "whatsapp_contacts": wa,
        "hot_leads": hot,
        "total_leads": len(leads),
    }
