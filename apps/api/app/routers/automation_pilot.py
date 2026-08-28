"""API + webhooks Automatización (IG/FB) — piloto."""

from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from app.config import get_settings
from app.deps.auth import require_user_id
from app.services.automation_pilot.gate import (
    automation_module_enabled,
    require_automation_module,
)
from app.services.automation_pilot import service as automation_service
from app.services.automation_pilot import store
from app.services.automation_pilot.worker import enqueue_meta_event
from app.services import supabase_db

logger = logging.getLogger(__name__)

webhook_router = APIRouter(prefix="/webhooks", tags=["automation-webhooks"])

auth_router = APIRouter(
    prefix="/v1/automation-pilot",
    tags=["automation-pilot"],
    dependencies=[Depends(require_automation_module)],
)


class PreviewBody(BaseModel):
    text: str = Field(..., min_length=8, max_length=2000)


class ConfirmBody(BaseModel):
    preview: dict[str, Any]
    activate: bool = False


class ToggleBody(BaseModel):
    status: str = Field(..., pattern="^(active|paused)$")


class EnsureCardBody(BaseModel):
    card_key: str
    activate: bool = False


def _verify_token() -> str:
    s = get_settings()
    return (
        (s.automation_webhook_verify_token or "").strip()
        or (s.whatsapp_verify_token or "").strip()
        or "ced-automation-verify"
    )


def _app_secret() -> str:
    s = get_settings()
    return (
        (s.instagram_app_secret or "").strip()
        or (s.meta_app_secret or "").strip()
    )


def _verify_meta_signature(request_body: bytes, signature_header: str | None) -> bool:
    secret = _app_secret()
    if not secret:
        # Dev / dry setup: allow if module on and no secret configured yet.
        logger.warning("[AUTOMATION:WEBHOOK] no app secret — skipping signature check")
        return True
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(
        secret.encode("utf-8"),
        request_body,
        hashlib.sha256,
    ).hexdigest()
    got = signature_header.split("=", 1)[-1].strip()
    return hmac.compare_digest(expected, got)


def _resolve_user_id_from_meta(*, page_id: str | None, ig_id: str | None) -> str | None:
    try:
        client = supabase_db.get_client()
        q = client.table("meta_connections").select("user_id, page_id, ig_user_id")
        res = q.execute()
        for row in res.data or []:
            if page_id and str(row.get("page_id") or "") == str(page_id):
                return str(row.get("user_id") or "") or None
            if ig_id and str(row.get("ig_user_id") or "") == str(ig_id):
                return str(row.get("user_id") or "") or None
    except Exception:  # noqa: BLE001
        logger.exception("[AUTOMATION] resolve user from meta failed")
    return None


def _hub_verify(
    hub_mode: str | None,
    hub_verify_token: str | None,
    hub_challenge: str | None,
) -> PlainTextResponse:
    if hub_mode == "subscribe" and hub_verify_token == _verify_token():
        return PlainTextResponse(content=hub_challenge or "", status_code=200)
    raise HTTPException(status_code=403, detail="Verify token inválido")


@webhook_router.get("/instagram")
@webhook_router.get("/facebook")
@webhook_router.get("/meta")
async def meta_webhook_verify(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
) -> PlainTextResponse:
    return _hub_verify(hub_mode, hub_verify_token, hub_challenge)


def _parse_messaging_and_comments(body: dict[str, Any]) -> list[dict[str, Any]]:
    """Normaliza payload Graph webhook → eventos internos."""
    events: list[dict[str, Any]] = []
    obj = str(body.get("object") or "")
    channel = "instagram" if obj == "instagram" else "facebook"
    for entry in body.get("entry") or []:
        if not isinstance(entry, dict):
            continue
        page_id = str(entry.get("id") or "") or None
        # Messenger / IG DMs
        for messaging in entry.get("messaging") or []:
            if not isinstance(messaging, dict):
                continue
            sender = (messaging.get("sender") or {}).get("id")
            message = messaging.get("message") or {}
            text = str(message.get("text") or "")
            if not sender:
                continue
            events.append(
                {
                    "channel": channel,
                    "event_type": "dm_new",
                    "contact_id": str(sender),
                    "text": text,
                    "page_id": page_id,
                    "raw": messaging,
                }
            )
        # Comments (changes field)
        for change in entry.get("changes") or []:
            if not isinstance(change, dict):
                continue
            field = str(change.get("field") or "")
            value = change.get("value") or {}
            if not isinstance(value, dict):
                continue
            if field in {"comments", "feed"} or "comment" in field:
                text = str(value.get("text") or value.get("message") or "")
                contact = (
                    str((value.get("from") or {}).get("id") or "")
                    or str(value.get("from_id") or "")
                    or "unknown"
                )
                media_id = str(
                    value.get("media_id")
                    or value.get("post_id")
                    or value.get("parent_id")
                    or ""
                ) or None
                events.append(
                    {
                        "channel": channel,
                        "event_type": "comment_new",
                        "contact_id": contact,
                        "text": text,
                        "media_id": media_id,
                        "page_id": page_id,
                        "ig_id": page_id if channel == "instagram" else None,
                        "display_name": str((value.get("from") or {}).get("name") or "")
                        or None,
                        "raw": change,
                    }
                )
    return events


async def _handle_meta_webhook(request: Request) -> dict[str, Any]:
    if not automation_module_enabled():
        # ACK 200 para no romper suscripción Meta; no procesar.
        return {"ok": True, "skipped": "module_disabled"}
    raw = await request.body()
    sig = request.headers.get("X-Hub-Signature-256")
    if not _verify_meta_signature(raw, sig):
        raise HTTPException(status_code=403, detail="Firma inválida")
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    parsed = _parse_messaging_and_comments(body if isinstance(body, dict) else {})
    enqueued = 0
    for ev in parsed:
        user_id = _resolve_user_id_from_meta(
            page_id=ev.get("page_id"),
            ig_id=ev.get("ig_id") or (ev.get("page_id") if ev.get("channel") == "instagram" else None),
        )
        if not user_id:
            logger.info(
                "[AUTOMATION:WEBHOOK] no user for page=%s channel=%s",
                ev.get("page_id"),
                ev.get("channel"),
            )
            continue
        ev["user_id"] = user_id
        enqueue_meta_event(ev)
        enqueued += 1
    return {"ok": True, "enqueued": enqueued}


@webhook_router.post("/instagram")
@webhook_router.post("/facebook")
@webhook_router.post("/meta")
async def meta_webhook_receive(request: Request) -> dict[str, Any]:
    return await _handle_meta_webhook(request)


# --- Panel autenticado ---


@auth_router.get("/status")
def automation_status(user_id: str = Depends(require_user_id)) -> dict[str, Any]:
    return automation_service.module_status(user_id)


@auth_router.get("/cards")
def automation_cards(user_id: str = Depends(require_user_id)) -> dict[str, Any]:
    return {"ok": True, "cards": automation_service.list_cards(user_id)}


@auth_router.get("/leads")
def automation_leads(user_id: str = Depends(require_user_id)) -> dict[str, Any]:
    return {"ok": True, "leads": store.list_leads(user_id)}


@auth_router.post("/cards/ensure")
def automation_ensure_card(
    body: EnsureCardBody,
    user_id: str = Depends(require_user_id),
) -> dict[str, Any]:
    return automation_service.ensure_card(user_id, body.card_key, activate=body.activate)


@auth_router.post("/automations/{automation_id}/status")
def automation_toggle(
    automation_id: str,
    body: ToggleBody,
    user_id: str = Depends(require_user_id),
) -> dict[str, Any]:
    return automation_service.set_card_status(user_id, automation_id, body.status)


@auth_router.post("/preview")
def automation_preview(
    body: PreviewBody,
    user_id: str = Depends(require_user_id),
) -> dict[str, Any]:
    return automation_service.preview_from_speech(user_id, body.text)


@auth_router.post("/confirm")
def automation_confirm(
    body: ConfirmBody,
    user_id: str = Depends(require_user_id),
) -> dict[str, Any]:
    return automation_service.confirm_from_preview(
        user_id,
        body.preview,
        activate=body.activate,
    )


@auth_router.get("/intent-check")
def automation_intent_check(
    text: str = Query(..., min_length=3),
    _user_id: str = Depends(require_user_id),
) -> dict[str, Any]:
    from app.services.automation_pilot.intents import (
        is_automation_config_intent,
        parse_automation_brief,
    )

    return {
        "ok": True,
        "is_intent": is_automation_config_intent(text),
        "preview": parse_automation_brief(text),
    }
