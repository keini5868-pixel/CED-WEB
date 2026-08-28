"""Motor de matching + ejecución (dry-run o live)."""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import quote

from app.config import get_settings
from app.services.automation_pilot.gate import automation_ig_fb_live_enabled
from app.services.automation_pilot import store

logger = logging.getLogger(__name__)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def keywords_match(text: str, keywords: list[str] | None) -> bool:
    if not keywords:
        return True
    blob = _norm(text)
    return any(_norm(k) and _norm(k) in blob for k in keywords)


def build_whatsapp_link(phone_e164: str, prefill: str) -> str:
    digits = re.sub(r"\D+", "", phone_e164 or "")
    if not digits:
        return ""
    return f"https://wa.me/{digits}?text={quote(prefill or '')}"


def match_automations(
    automations: list[dict[str, Any]],
    *,
    event_type: str,
    text: str,
    media_id: str | None = None,
) -> list[dict[str, Any]]:
    """event_type: dm_new | comment_new"""
    matched: list[dict[str, Any]] = []
    for row in automations:
        ttype = str(row.get("trigger_type") or "")
        cfg = row.get("trigger_config") or {}
        if not isinstance(cfg, dict):
            cfg = {}
        if event_type == "dm_new" and ttype in {"dm_new", "dm_keyword"}:
            if ttype == "dm_keyword" and not keywords_match(text, cfg.get("keywords")):
                continue
            matched.append(row)
        elif event_type == "comment_new" and ttype in {"comment_keyword", "comment_any"}:
            if ttype == "comment_keyword" and not keywords_match(text, cfg.get("keywords")):
                continue
            post_ids = cfg.get("post_ids") or cfg.get("media_ids")
            if post_ids and media_id and media_id not in post_ids:
                continue
            matched.append(row)
    return matched


def render_action_text(action: dict[str, Any], *, context: dict[str, str]) -> str:
    template = str(action.get("reply_text") or action.get("notify_text") or "").strip()
    out = template
    for key, val in context.items():
        out = out.replace("{" + key + "}", val)
    return out


def execute_matched(
    *,
    user_id: str,
    channel: str,
    event_type: str,
    contact_id: str,
    text: str,
    payload: dict[str, Any],
    media_id: str | None = None,
    display_name: str | None = None,
) -> list[dict[str, Any]]:
    """Procesa automations activas. IG/FB respetan dry-run si LIVE=OFF."""
    live = automation_ig_fb_live_enabled() if channel in {"instagram", "facebook"} else True
    dry_run = not live
    results: list[dict[str, Any]] = []

    actives = [
        a
        for a in store.list_active_for_channel(channel)
        if str(a.get("user_id") or "") == user_id
    ]
    matched = match_automations(
        actives,
        event_type=event_type,
        text=text,
        media_id=media_id,
    )

    store.upsert_lead(
        user_id,
        contact_id=contact_id,
        channel_origen=channel,
        display_name=display_name,
        event={"type": event_type, "text": (text or "")[:240]},
    )

    settings = get_settings()
    wa_phone = (getattr(settings, "automation_default_whatsapp_e164", "") or "").strip()
    fitline = (settings.opportunities_fitline_sponsor_url or "").strip()

    if not matched:
        store.log_event(
            {
                "user_id": user_id,
                "channel": channel,
                "event_type": event_type,
                "contact_id": contact_id,
                "payload": payload,
                "matched": False,
                "dry_run": dry_run,
            }
        )
        return results

    for auto in matched:
        action = auto.get("action_config") or {}
        if not isinstance(action, dict):
            action = {}
        action_type = str(action.get("type") or "reply_text")
        prefill = str(action.get("wa_prefill") or "Hola, vengo de tus redes")
        wa_link = build_whatsapp_link(wa_phone, prefill)
        body = render_action_text(
            action,
            context={
                "whatsapp_link": wa_link or "[configura WhatsApp]",
                "fitline_link": fitline or "[enlace FitLine]",
                "contact_id": contact_id,
                "channel": channel,
            },
        )
        action_result: dict[str, Any] = {
            "action_type": action_type,
            "body": body,
            "dry_run": dry_run,
            "sent": False,
        }

        if action.get("tag"):
            store.upsert_lead(
                user_id,
                contact_id=contact_id,
                channel_origen=channel,
                etiqueta=str(action.get("tag")),
            )

        if not dry_run and body:
            try:
                sent = _send_platform_reply(
                    channel=channel,
                    user_id=user_id,
                    contact_id=contact_id,
                    text=body,
                    payload=payload,
                    action_type=action_type,
                )
                action_result["sent"] = bool(sent.get("ok"))
                action_result["send"] = sent
            except Exception as exc:  # noqa: BLE001
                logger.exception("[AUTOMATION] send failed")
                action_result["error"] = str(exc)[:200]

        store.log_event(
            {
                "user_id": user_id,
                "automation_id": auto.get("id"),
                "channel": channel,
                "event_type": event_type,
                "contact_id": contact_id,
                "payload": payload,
                "matched": True,
                "dry_run": dry_run,
                "action_result": action_result,
            }
        )
        if auto.get("id"):
            store.touch_triggered(str(auto["id"]))
        results.append({"automation": auto, "result": action_result})

    return results


def _send_platform_reply(
    *,
    channel: str,
    user_id: str,
    contact_id: str,
    text: str,
    payload: dict[str, Any],
    action_type: str,
) -> dict[str, Any]:
    """Envío real — stub seguro hasta Advanced Access Meta messaging."""
    # Fase 1: registrar intención; Graph send se activa con LIVE + tokens Page.
    logger.info(
        "[AUTOMATION:LIVE] channel=%s user=%s contact=%s type=%s text=%s",
        channel,
        user_id[:8],
        contact_id[:24],
        action_type,
        text[:80],
    )
    return {
        "ok": True,
        "mode": "queued_stub",
        "note": (
            "Envío Graph (IG/FB messaging) pendiente de Advanced Access; "
            "evento registrado para auditoría."
        ),
        "payload_preview": {
            "channel": channel,
            "contact_id": contact_id,
            "text": text[:500],
            "source": payload.get("object"),
        },
    }
