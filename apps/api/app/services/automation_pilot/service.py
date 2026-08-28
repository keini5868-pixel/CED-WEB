"""Servicio de panel — tarjetas, cuotas, confirmación conversacional."""

from __future__ import annotations

import logging
from typing import Any

from app.domain.plans import PlanId
from app.services.automation_pilot.catalog import CURATED_CARDS, NURTURE_DEFAULT_DAYS
from app.services.automation_pilot.gate import (
    automation_ig_fb_live_enabled,
    automation_module_enabled,
)
from app.services.automation_pilot.intents import parse_automation_brief
from app.services.automation_pilot import store

logger = logging.getLogger(__name__)

# Starter 2, Pro 5, Elite/Founding unlimited (-1)
_PLAN_ACTIVE_CAPS: dict[str, int] = {
    PlanId.FREE_BASIC.value: 0,
    PlanId.STARTER.value: 2,
    PlanId.PRO.value: 5,
    PlanId.ELITE.value: -1,
    PlanId.FOUNDING.value: -1,
    PlanId.ELITE_FOUNDING.value: -1,
    PlanId.ELITE_REGULAR.value: -1,
}


def active_cap_for_user(user_id: str) -> int:
    plan_id = PlanId.FREE_BASIC.value
    try:
        from app.services import supabase_db

        sub = supabase_db.get_subscription(user_id) or {}
        plan_id = str(sub.get("plan_id") or plan_id)
    except Exception:  # noqa: BLE001
        pass
    return int(_PLAN_ACTIVE_CAPS.get(plan_id, 2))


def module_status(user_id: str) -> dict[str, Any]:
    stats = store.narrative_stats(user_id)
    cap = active_cap_for_user(user_id)
    active = store.count_active(user_id)
    narrative = (
        f"{stats['instagram_contacts']} personas te escribieron o comentaron en Instagram, "
        f"{stats['facebook_contacts']} en Facebook, "
        f"{stats['whatsapp_contacts']} llegaron a WhatsApp; "
        f"{stats['hot_leads']} leads calientes detectados."
    )
    return {
        "ok": True,
        "enabled": automation_module_enabled(),
        "ig_fb_live": automation_ig_fb_live_enabled(),
        "dry_run": not automation_ig_fb_live_enabled(),
        "active_count": active,
        "active_cap": cap,
        "stats": stats,
        "narrative": narrative,
        "nurture_default_days": NURTURE_DEFAULT_DAYS,
        "meta_scopes_note": (
            "Para DMs en producción se requieren permisos "
            "instagram_manage_messages / pages_messaging (Advanced Access). "
            "Comentarios usan instagram_manage_comments ya solicitado en OAuth."
        ),
    }


def list_cards(user_id: str) -> list[dict[str, Any]]:
    existing = store.list_automations(user_id)
    by_key = {str(r.get("card_key") or ""): r for r in existing if r.get("card_key")}
    cards: list[dict[str, Any]] = []
    for spec in CURATED_CARDS:
        key = str(spec["card_key"])
        row = by_key.get(key)
        cards.append(
            {
                "card_key": key,
                "name": spec["name"],
                "description": spec["description"],
                "channel": spec["channel"],
                "trigger_type": spec["trigger_type"],
                "status": (row or {}).get("status") or "paused",
                "id": (row or {}).get("id"),
                "last_triggered_at": (row or {}).get("last_triggered_at"),
                "configured": bool(row),
            }
        )
    # Custom rows without card_key
    for row in existing:
        if row.get("card_key"):
            continue
        cards.append(
            {
                "card_key": None,
                "name": row.get("name") or "Personalizada",
                "description": "Automatización creada con CED",
                "channel": row.get("channel"),
                "trigger_type": row.get("trigger_type"),
                "status": row.get("status"),
                "id": row.get("id"),
                "last_triggered_at": row.get("last_triggered_at"),
                "configured": True,
            }
        )
    return cards


def ensure_card(user_id: str, card_key: str, *, activate: bool = False) -> dict[str, Any]:
    spec = next((c for c in CURATED_CARDS if c["card_key"] == card_key), None)
    if not spec:
        return {"ok": False, "error": "Tarjeta desconocida"}
    existing = store.list_automations(user_id)
    row = next((r for r in existing if r.get("card_key") == card_key), None)
    status = "active" if activate else ((row or {}).get("status") or "paused")
    if activate:
        cap = active_cap_for_user(user_id)
        active = store.count_active(user_id)
        if cap >= 0 and active >= cap and (not row or row.get("status") != "active"):
            return {
                "ok": False,
                "error": f"Límite de automatizaciones activas alcanzado ({cap}).",
                "code": "quota",
            }
    payload = {
        "id": (row or {}).get("id"),
        "channel": spec["channel"],
        "trigger_type": spec["trigger_type"],
        "name": spec["name"],
        "card_key": card_key,
        "trigger_config": spec["default_trigger"],
        "action_config": spec["default_action"],
        "status": status,
    }
    saved = store.upsert_automation(user_id, payload)
    if not saved:
        return {"ok": False, "error": "No se pudo guardar (¿migración 040 aplicada?)"}
    return {"ok": True, "automation": saved}


def set_card_status(user_id: str, automation_id: str, status: str) -> dict[str, Any]:
    if status == "active":
        cap = active_cap_for_user(user_id)
        active = store.count_active(user_id)
        current = store.get_automation(user_id, automation_id)
        if (
            cap >= 0
            and active >= cap
            and current
            and current.get("status") != "active"
        ):
            return {
                "ok": False,
                "error": f"Límite de automatizaciones activas alcanzado ({cap}).",
                "code": "quota",
            }
    saved = store.set_automation_status(user_id, automation_id, status)
    if not saved:
        return {"ok": False, "error": "No se pudo actualizar"}
    return {"ok": True, "automation": saved}


def preview_from_speech(user_id: str, text: str) -> dict[str, Any]:
    _ = user_id
    brief = parse_automation_brief(text)
    if not brief:
        return {
            "ok": False,
            "error": (
                "No reconocí una automatización. Pruebe: "
                "«cuando alguien comente info en Instagram, responde con el link de WhatsApp»."
            ),
        }
    return {"ok": True, "preview": brief, "needs_confirmation": True}


def confirm_from_preview(user_id: str, preview: dict[str, Any], *, activate: bool) -> dict[str, Any]:
    card_key = str(preview.get("card_key") or "")
    base = ensure_card(user_id, card_key, activate=False)
    if not base.get("ok"):
        return base
    auto = base["automation"]
    payload = {
        "id": auto.get("id"),
        "channel": preview.get("channel") or auto.get("channel"),
        "trigger_type": preview.get("trigger_type") or auto.get("trigger_type"),
        "name": preview.get("name") or auto.get("name"),
        "card_key": card_key or auto.get("card_key"),
        "trigger_config": preview.get("trigger_config") or auto.get("trigger_config"),
        "action_config": preview.get("action_config") or auto.get("action_config"),
        "status": "active" if activate else "paused",
    }
    if activate:
        cap = active_cap_for_user(user_id)
        if cap >= 0 and store.count_active(user_id) >= cap and auto.get("status") != "active":
            return {
                "ok": False,
                "error": f"Límite de automatizaciones activas alcanzado ({cap}).",
                "code": "quota",
            }
    saved = store.upsert_automation(user_id, payload)
    if not saved:
        return {"ok": False, "error": "No se pudo confirmar"}
    return {
        "ok": True,
        "automation": saved,
        "message": (
            f"Listo. «{saved.get('name')}» quedó "
            f"{'activa' if saved.get('status') == 'active' else 'en pausa'}. "
            + (
                "Modo dry-run: no se envían respuestas reales a IG/FB hasta "
                "AUTOMATION_IG_FB_LIVE_ENABLED=true."
                if not automation_ig_fb_live_enabled()
                and saved.get("channel") in {"instagram", "facebook"}
                else ""
            )
        ).strip(),
    }
