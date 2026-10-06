"""Automatización Instagram DM — ManyChat + cerebro CED por usuario."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.config import get_settings
from app.deps.auth import require_user_id
from app.deps.plan_access import manychat_access
from app.services import manychat_brain as brain
from app.services import manychat_store as store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/manychat", tags=["manychat"])
webhook_router = APIRouter(prefix="/webhooks", tags=["manychat-webhooks"])

INACTIVE_REPLY = (
    "Este canal aún no está activo. El dueño debe encender Automatización en CED."
)


class BehaviorBody(BaseModel):
    model_config = {"extra": "ignore"}

    enabled: bool | None = None
    role: str = Field(default="closer", max_length=24)
    tone: str = Field(default="cercano", max_length=24)
    mission: str = Field(default="", max_length=8000)
    ask_lines: str = Field(default="", max_length=4000)
    objections: str = Field(default="", max_length=4000)
    never_say: str = Field(default="", max_length=2000)
    cta_when: str = Field(default="ready", max_length=16)
    cta_url: str = Field(default="", max_length=2000)
    cta_label: str = Field(default="", max_length=120)


def _public_base() -> str:
    return get_settings().api_public_url.strip().rstrip("/")


def _webhook_url(secret: str) -> str:
    return f"{_public_base()}/webhooks/manychat/{secret}"


def _status_payload(user_id: str) -> dict[str, Any]:
    acc = store.ensure_account(user_id)
    allowed, reason = manychat_access(user_id)
    return {
        "ok": True,
        "allowed": allowed,
        "access_reason": reason,
        "webhook_url": _webhook_url(acc["webhook_secret"]),
        "webhook_secret": acc["webhook_secret"],
        "enabled": bool(acc.get("enabled")),
        "role": acc.get("role"),
        "tone": acc.get("tone"),
        "mission": acc.get("mission") or "",
        "ask_lines": acc.get("ask_lines") or "",
        "objections": acc.get("objections") or "",
        "never_say": acc.get("never_say") or "",
        "cta_when": acc.get("cta_when"),
        "cta_url": acc.get("cta_url") or "",
        "cta_label": acc.get("cta_label") or "",
        "presets": {
            key: {"label": spec["label"], "mission": spec["mission"]}
            for key, spec in brain.ROLE_PRESETS.items()
        },
        "setup": [
            "En ManyChat crea un flujo para comentario y otro para DM default.",
            "Añade un Dynamic Block (Dev Tools) que haga POST a la URL de este panel.",
            "En el body manda last_input_text y el id del contacto.",
            "Activa el interruptor cuando la plantilla y el enlace estén listos.",
        ],
        "messages": store.list_messages(user_id, limit=16),
    }


@router.get("/status")
def get_status(user_id: str = Depends(require_user_id)) -> dict[str, Any]:
    return _status_payload(user_id)


@router.put("/behavior")
@router.post("/behavior")
async def put_behavior(
    request: Request,
    user_id: str = Depends(require_user_id),
) -> dict[str, Any]:
    try:
        raw = await request.json()
    except Exception:
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    try:
        body = BehaviorBody.model_validate(raw)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail="No pude leer la plantilla. Recarga la página e inténtalo otra vez.",
        ) from exc
    allowed, reason = manychat_access(user_id)
    if body.enabled is True and not allowed:
        raise HTTPException(
            status_code=403,
            detail=(
                "Automatización ManyChat requiere plan Pro, Élite, Founding o Cierre."
                if reason != "trial_expired"
                else "Tu prueba terminó. Elige un plan para activar Automatización."
            ),
        )
    try:
        store.save_account(
            user_id,
            {
                "enabled": body.enabled
                if body.enabled is not None
                else store.ensure_account(user_id)["enabled"],
                "role": body.role,
                "tone": body.tone,
                "mission": body.mission,
                "ask_lines": body.ask_lines,
                "objections": body.objections,
                "never_say": body.never_say,
                "cta_when": body.cta_when,
                "cta_url": body.cta_url,
                "cta_label": body.cta_label,
            },
        )
    except Exception:
        logger.exception("[MANYCHAT] save behavior failed")
        raise HTTPException(status_code=500, detail="No se pudo guardar la plantilla.")
    return _status_payload(user_id)


@router.post("/secret/rotate")
def rotate_secret(user_id: str = Depends(require_user_id)) -> dict[str, Any]:
    store.rotate_secret(user_id)
    return _status_payload(user_id)


def _payload_from_request(data: Any) -> dict[str, Any]:
    if isinstance(data, dict):
        return data
    return {}


def _handle_inbound(secret: str, payload: dict[str, Any]) -> dict[str, Any]:
    acc = store.get_account_by_secret(secret)
    if not acc:
        raise HTTPException(status_code=401, detail="Secreto ManyChat inválido.")
    callback = _webhook_url(acc["webhook_secret"])
    if not acc.get("enabled"):
        return brain.manychat_response(
            text=INACTIVE_REPLY,
            callback_url=callback,
            secret=acc["webhook_secret"],
        )
    reply = brain.reply_as_ced(
        owner_user_id=str(acc["user_id"]),
        account=acc,
        payload=payload,
    )
    return brain.manychat_response(
        text=reply,
        callback_url=callback,
        secret=acc["webhook_secret"],
    )


@webhook_router.post("/manychat/{secret}")
async def manychat_webhook_secret(secret: str, request: Request) -> dict[str, Any]:
    try:
        data = await request.json()
    except Exception:
        data = {}
    return _handle_inbound(secret, _payload_from_request(data))


@webhook_router.post("/manychat")
async def manychat_webhook_header(request: Request) -> dict[str, Any]:
    try:
        data = await request.json()
    except Exception:
        data = {}
    payload = _payload_from_request(data)
    secret = (
        request.headers.get("x-ced-manychat-secret")
        or request.headers.get("x-ced-secret")
        or str(payload.get("secret") or "")
    ).strip()
    return _handle_inbound(secret, payload)
