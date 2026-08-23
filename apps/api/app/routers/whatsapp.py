"""WhatsApp Business — conexión por usuario, webhook Cloud API y flujos."""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from app.config import get_settings
from app.deps.auth import require_user_id
from app.deps.plan_access import require_whatsapp
from app.services import supabase_db
from app.services.whatsapp_cloud import (
    WhatsAppCloudError,
    create_message_template,
    exchange_oauth_code,
    fetch_phone_numbers,
    inbound_text_events,
    list_message_templates,
    send_template_message,
    send_text_message,
    subscribe_waba_webhooks,
    verify_webhook_signature,
)
from app.services.whatsapp_flows import (
    is_opt_in_message,
    is_stop_message,
    match_flow,
    uses_ced_chat,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/whatsapp", tags=["whatsapp"])

STOP_REPLY = (
    "Listo, no te enviaré más respuestas automáticas. "
    "Si quieres volver, escribe HOLA."
)
OPT_IN_REPLY = "Gracias. Las respuestas automáticas están activas de nuevo."


class ConnectBody(BaseModel):
    code: str | None = None
    waba_id: str | None = None
    phone_number_id: str | None = None
    access_token: str | None = None


class AutomationBody(BaseModel):
    goal: str = Field(default="", max_length=2000)
    cta_url: str = Field(default="", max_length=500)
    cta_label: str = Field(default="", max_length=120)


class FlowCreateBody(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    trigger_type: str = Field(default="keyword", max_length=20)
    keywords: str = Field(default="", max_length=500)
    reply_text: str = Field(default="", max_length=1000)
    enabled: bool = True
    priority: int = Field(default=100, ge=0, le=9999)


class FlowPatchBody(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    trigger_type: str | None = Field(default=None, max_length=20)
    keywords: str | None = Field(default=None, max_length=500)
    reply_text: str | None = Field(default=None, max_length=1000)
    enabled: bool | None = None
    priority: int | None = Field(default=None, ge=0, le=9999)


def _ensure_ced_ai_flow(user_id: str) -> None:
    flows = supabase_db.list_whatsapp_flows(user_id)
    if any(str(f.get("trigger_type") or "").lower() in ("ced_ai", "ai") for f in flows):
        return
    supabase_db.insert_whatsapp_flow(
        user_id,
        {
            "name": "CED (chat)",
            "trigger_type": "ced_ai",
            "keywords": "",
            "reply_text": "__CED_AI__",
            "enabled": True,
            "priority": 50,
        },
    )


def _seed_default_flows(user_id: str) -> None:
    existing = supabase_db.list_whatsapp_flows(user_id)
    if existing:
        _ensure_ced_ai_flow(user_id)
        return
    supabase_db.insert_whatsapp_flow(
        user_id,
        {
            "name": "CED (chat)",
            "trigger_type": "ced_ai",
            "keywords": "",
            "reply_text": "__CED_AI__",
            "enabled": True,
            "priority": 900,
        },
    )


@router.get("/connect/config")
def whatsapp_connect_config(user_id: str = Depends(require_user_id)) -> dict:
    require_whatsapp(user_id)
    settings = get_settings()
    app_id = settings.meta_app_id.strip()
    config_id = settings.whatsapp_embedded_signup_config_id.strip() or (
        settings.meta_login_config_id.strip()
    )
    if not app_id:
        raise HTTPException(status_code=503, detail="META_APP_ID no configurado.")
    return {
        "app_id": app_id,
        "config_id": config_id or None,
        "api_version": settings.meta_api_version.strip() or "v21.0",
        "webhook_url": f"{settings.api_public_url.rstrip('/')}/v1/whatsapp/webhook",
        "verify_token_configured": bool(settings.whatsapp_verify_token.strip()),
    }


@router.get("/status")
def whatsapp_status(user_id: str = Depends(require_user_id)) -> dict:
    acc = supabase_db.get_whatsapp_account(user_id)
    if not acc:
        return {"connected": False}
    return {
        "connected": True,
        "display_phone": acc.get("display_phone"),
        "verified_name": acc.get("verified_name"),
        "phone_number_id": acc.get("phone_number_id"),
        "waba_id": acc.get("waba_id"),
        "status": acc.get("status") or "active",
        "automation_goal": acc.get("automation_goal") or "",
        "automation_cta_url": acc.get("automation_cta_url") or "",
        "automation_cta_label": acc.get("automation_cta_label") or "",
    }


@router.patch("/automation")
def whatsapp_automation(
    body: AutomationBody,
    user_id: str = Depends(require_user_id),
) -> dict:
    require_whatsapp(user_id)
    acc = supabase_db.get_whatsapp_account(user_id)
    if not acc:
        raise HTTPException(status_code=400, detail="Conecta WhatsApp primero.")
    updated = supabase_db.update_whatsapp_account(
        user_id,
        {
            "automation_goal": body.goal.strip(),
            "automation_cta_url": body.cta_url.strip(),
            "automation_cta_label": body.cta_label.strip(),
        },
    )
    if not updated:
        raise HTTPException(
            status_code=503,
            detail="No pude guardar el objetivo. Ejecuta la migración 037_whatsapp_automation_goal.sql en Supabase.",
        )
    return {
        "ok": True,
        "automation_goal": updated.get("automation_goal") or "",
        "automation_cta_url": updated.get("automation_cta_url") or "",
        "automation_cta_label": updated.get("automation_cta_label") or "",
    }


@router.post("/connect")
def whatsapp_connect(
    body: ConnectBody,
    user_id: str = Depends(require_user_id),
) -> dict:
    require_whatsapp(user_id)
    token = (body.access_token or "").strip()
    if body.code and not token:
        try:
            token = exchange_oauth_code(body.code)
        except WhatsAppCloudError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not token:
        raise HTTPException(
            status_code=400,
            detail="Falta el código de Meta o el token de WhatsApp.",
        )

    waba_id = (body.waba_id or "").strip()
    phone_number_id = (body.phone_number_id or "").strip()
    display_phone = ""
    verified_name = ""

    if waba_id:
        try:
            numbers = fetch_phone_numbers(waba_id, token)
        except WhatsAppCloudError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not phone_number_id and numbers:
            first = numbers[0]
            phone_number_id = str(first.get("id") or "")
            display_phone = str(first.get("display_phone_number") or "")
            verified_name = str(first.get("verified_name") or "")
        else:
            for item in numbers:
                if str(item.get("id") or "") == phone_number_id:
                    display_phone = str(item.get("display_phone_number") or "")
                    verified_name = str(item.get("verified_name") or "")
                    break
        subscribe_waba_webhooks(waba_id, token)

    if not phone_number_id:
        raise HTTPException(
            status_code=400,
            detail="No llegó el ID del número de WhatsApp. Completa el alta en Meta e inténtalo de nuevo.",
        )

    other = supabase_db.get_whatsapp_account_by_phone_number_id(phone_number_id)
    if other and str(other.get("user_id")) != user_id:
        raise HTTPException(
            status_code=409,
            detail="Ese número ya está vinculado a otra cuenta CED.",
        )

    supabase_db.upsert_whatsapp_account(
        user_id,
        {
            "waba_id": waba_id or None,
            "phone_number_id": phone_number_id,
            "display_phone": display_phone or None,
            "verified_name": verified_name or None,
            "access_token": token,
            "status": "active",
            "connected_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    _seed_default_flows(user_id)
    _ensure_ced_ai_flow(user_id)
    return {
        "ok": True,
        "connected": True,
        "display_phone": display_phone or None,
        "phone_number_id": phone_number_id,
    }


@router.delete("/connect")
def whatsapp_disconnect(user_id: str = Depends(require_user_id)) -> dict:
    require_whatsapp(user_id)
    supabase_db.delete_whatsapp_account(user_id)
    return {"ok": True, "connected": False}


@router.get("/flows")
def list_flows(user_id: str = Depends(require_user_id)) -> dict:
    require_whatsapp(user_id)
    return {"flows": supabase_db.list_whatsapp_flows(user_id)}


@router.post("/flows")
def create_flow(body: FlowCreateBody, user_id: str = Depends(require_user_id)) -> dict:
    require_whatsapp(user_id)
    kind = body.trigger_type.strip().lower()
    if kind not in ("keyword", "catch_all", "catchall", "default", "ced_ai", "ai"):
        raise HTTPException(status_code=400, detail="Tipo de flujo no válido.")
    if kind == "keyword" and not body.keywords.strip():
        raise HTTPException(status_code=400, detail="Indica al menos una palabra clave.")
    kind_store = (
        "ced_ai"
        if kind in ("ced_ai", "ai")
        else ("catch_all" if kind in ("catchall", "default") else kind)
    )
    reply = body.reply_text.strip() or ("__CED_AI__" if kind_store == "ced_ai" else "")
    if kind_store != "ced_ai" and not reply:
        raise HTTPException(status_code=400, detail="Indica el texto de respuesta.")
    row = supabase_db.insert_whatsapp_flow(
        user_id,
        {
            "name": body.name.strip(),
            "trigger_type": kind_store,
            "keywords": body.keywords.strip(),
            "reply_text": reply,
            "enabled": body.enabled,
            "priority": body.priority,
        },
    )
    if not row:
        raise HTTPException(status_code=503, detail="No pude guardar el flujo.")
    return {"ok": True, "flow": row}


@router.patch("/flows/{flow_id}")
def patch_flow(
    flow_id: str,
    body: FlowPatchBody,
    user_id: str = Depends(require_user_id),
) -> dict:
    require_whatsapp(user_id)
    patch: dict[str, Any] = {}
    if body.name is not None:
        patch["name"] = body.name.strip()
    if body.trigger_type is not None:
        kind = body.trigger_type.strip().lower()
        patch["trigger_type"] = "catch_all" if kind in ("catchall", "default") else kind
    if body.keywords is not None:
        patch["keywords"] = body.keywords.strip()
    if body.reply_text is not None:
        patch["reply_text"] = body.reply_text.strip()
    if body.enabled is not None:
        patch["enabled"] = body.enabled
    if body.priority is not None:
        patch["priority"] = body.priority
    if not patch:
        raise HTTPException(status_code=400, detail="Nada que actualizar.")
    row = supabase_db.update_whatsapp_flow(user_id, flow_id, patch)
    if not row:
        raise HTTPException(status_code=404, detail="Flujo no encontrado.")
    return {"ok": True, "flow": row}


@router.delete("/flows/{flow_id}")
def remove_flow(flow_id: str, user_id: str = Depends(require_user_id)) -> dict:
    require_whatsapp(user_id)
    supabase_db.delete_whatsapp_flow(user_id, flow_id)
    return {"ok": True}


@router.get("/messages")
def list_messages(
    user_id: str = Depends(require_user_id),
    limit: int = Query(default=40, ge=1, le=100),
) -> dict:
    require_whatsapp(user_id)
    raw = supabase_db.list_whatsapp_messages(user_id, limit=limit)
    messages = []
    for row in raw:
        messages.append(
            {
                "id": row.get("id"),
                "direction": row.get("direction") or row.get("direction"),
                "wa_from": row.get("wa_from"),
                "wa_to": row.get("wa_to"),
                "body": row.get("body"),
                "created_at": row.get("created_at"),
            }
        )
    return {"messages": messages}


class SendTextBody(BaseModel):
    to: str = Field(min_length=8, max_length=20)
    body: str = Field(min_length=1, max_length=4096)


class TemplateCreateBody(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    language: str = Field(default="es", max_length=12)
    body: str = Field(min_length=1, max_length=1024)
    category: str = Field(default="UTILITY", max_length=20)


class TemplateSendBody(BaseModel):
    to: str = Field(min_length=8, max_length=32)
    name: str = Field(min_length=1, max_length=80)
    language: str = Field(default="es", max_length=12)
    body_params: list[str] = Field(default_factory=list)


def _require_account(user_id: str) -> dict[str, Any]:
    acc = supabase_db.get_whatsapp_account(user_id)
    if not acc:
        raise HTTPException(status_code=400, detail="Conecta WhatsApp primero.")
    return acc


def _account_token(acc: dict[str, Any]) -> str:
    return str(acc.get("access_token") or acc.get("access_token") or "").strip()


def _account_phone(acc: dict[str, Any]) -> str:
    return str(acc.get("display_phone") or acc.get("display_phone") or "")


@router.post("/send")
def send_outbound(body: SendTextBody, user_id: str = Depends(require_user_id)) -> dict:
    require_whatsapp(user_id)
    acc = _require_account(user_id)
    token = _account_token(acc)
    phone_number_id = str(acc.get("phone_number_id") or "")
    to = "".join(ch for ch in body.to if ch.isdigit())
    if not token or not phone_number_id:
        raise HTTPException(status_code=400, detail="Falta token o número de WhatsApp.")
    try:
        send_text_message(
            phone_number_id=phone_number_id,
            access_token=token,
            to=to,
            body=body.body.strip(),
        )
    except WhatsAppCloudError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    supabase_db.insert_whatsapp_message(
        {
            "user_id": user_id,
            "direction": "out",
            "wa_from": _account_phone(acc),
            "wa_to": to,
            "body": body.body.strip(),
        }
    )
    return {"ok": True}


@router.get("/templates")
def list_templates(user_id: str = Depends(require_user_id)) -> dict:
    require_whatsapp(user_id)
    acc = _require_account(user_id)
    waba_id = str(acc.get("waba_id") or "").strip()
    token = _account_token(acc)
    if not waba_id or not token:
        raise HTTPException(status_code=400, detail="Falta WABA o token.")
    try:
        items = list_message_templates(waba_id, token)
    except WhatsAppCloudError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"templates": items}


@router.post("/templates")
def create_template(body: TemplateCreateBody, user_id: str = Depends(require_user_id)) -> dict:
    require_whatsapp(user_id)
    acc = _require_account(user_id)
    waba_id = str(acc.get("waba_id") or "").strip()
    token = _account_token(acc)
    if not waba_id or not token:
        raise HTTPException(status_code=400, detail="Falta WABA o token.")
    try:
        created = create_message_template(
            waba_id,
            token,
            name=body.name,
            language=body.language,
            body=body.body,
            category=body.category,
        )
    except WhatsAppCloudError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "template": created}


@router.post("/templates/send")
def send_template(body: TemplateSendBody, user_id: str = Depends(require_user_id)) -> dict:
    require_whatsapp(user_id)
    acc = _require_account(user_id)
    token = _account_token(acc)
    phone_number_id = str(acc.get("phone_number_id") or "")
    to = "".join(ch for ch in body.to if ch.isdigit())
    if not token or not phone_number_id:
        raise HTTPException(status_code=400, detail="Falta token o número de WhatsApp.")
    try:
        send_template_message(
            phone_number_id=phone_number_id,
            access_token=token,
            to=to,
            template_name=body.name,
            language=body.language,
            body_params=body.body_params,
        )
    except WhatsAppCloudError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    supabase_db.insert_whatsapp_message(
        {
            "user_id": user_id,
            "direction": "out",
            "wa_from": _account_phone(acc),
            "wa_to": to,
            "body": f"[plantilla {body.name}]",
        }
    )
    return {"ok": True}


@router.get("/webhook")
def whatsapp_webhook_verify(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
) -> PlainTextResponse:
    expected = get_settings().whatsapp_verify_token.strip()
    if hub_mode == "subscribe" and expected and hub_verify_token == expected:
        return PlainTextResponse(content=hub_challenge or "", status_code=200)
    raise HTTPException(status_code=403, detail="Verify token inválido.")


@router.post("/webhook")
async def whatsapp_webhook(request: Request) -> dict:
    raw = await request.body()
    sig = request.headers.get("x-hub-signature-256")
    if not verify_webhook_signature(raw, sig):
        raise HTTPException(status_code=403, detail="Firma webhook inválida.")
    try:
        payload = json.loads(raw.decode("utf-8") or "{}")
    except Exception:  # noqa: BLE001
        return {"ok": True}
    if not isinstance(payload, dict):
        return {"ok": True}
    threading.Thread(target=_handle_inbound, args=(payload,), daemon=True).start()
    return {"ok": True}


def _handle_inbound(payload: dict[str, Any]) -> None:
    from app.services.whatsapp_ai import reply_as_ced_chat

    for event in inbound_text_events(payload):
        phone_number_id = event["phone_number_id"]
        acc = supabase_db.get_whatsapp_account_by_phone_number_id(phone_number_id)
        if not acc:
            logger.info("[WA] inbound sin cuenta phone_number_id=%s", phone_number_id[:12])
            continue
        user_id = str(acc.get("user_id") or "")
        _ensure_ced_ai_flow(user_id)
        token = _account_token(acc)
        wa_from = event["from"]
        body = event["body"]
        wamid = event["wamid"]
        inserted = supabase_db.insert_whatsapp_message(
            {
                "user_id": user_id,
                "wamid": wamid,
                "direction": "in",
                "wa_from": wa_from,
                "wa_to": _account_phone(acc),
                "body": body,
                "raw": payload,
            }
        )
        if not inserted:
            continue
        now = datetime.now(timezone.utc).isoformat()
        contact = supabase_db.get_whatsapp_contact(user_id, wa_from) or {}
        opted_out = bool(contact.get("opted_out") or contact.get("opted_out"))

        reply = ""
        flow_id = None
        if is_stop_message(body):
            supabase_db.upsert_whatsapp_contact(
                user_id, wa_from, {"opted_out": True, "last_inbound_at": now}
            )
            reply = STOP_REPLY
        elif opted_out and is_opt_in_message(body):
            supabase_db.upsert_whatsapp_contact(
                user_id, wa_from, {"opted_out": False, "last_inbound_at": now}
            )
            reply = OPT_IN_REPLY
        elif opted_out:
            supabase_db.upsert_whatsapp_contact(
                user_id, wa_from, {"last_inbound_at": now}
            )
            continue
        else:
            supabase_db.upsert_whatsapp_contact(
                user_id, wa_from, {"opted_out": False, "last_inbound_at": now}
            )
            flow = match_flow(supabase_db.list_whatsapp_flows(user_id), body)
            flow_id = (flow or {}).get("id")
            if uses_ced_chat(flow):
                reply = reply_as_ced_chat(
                    owner_user_id=user_id,
                    wa_from=wa_from,
                    text=body,
                )
            else:
                reply = str((flow or {}).get("reply_text") or "").strip()

        if not reply or not token:
            continue
        try:
            send_text_message(
                phone_number_id=phone_number_id,
                access_token=token,
                to=wa_from,
                body=reply,
            )
        except WhatsAppCloudError:
            logger.warning("[WA] send failed user=%s", user_id[:8], exc_info=True)
            continue
        supabase_db.insert_whatsapp_message(
            {
                "user_id": user_id,
                "direction": "out",
                "wa_from": _account_phone(acc),
                "wa_to": wa_from,
                "body": reply,
                "flow_id": flow_id,
            }
        )
