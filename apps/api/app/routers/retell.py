"""Retell AI — registro de llamadas, webhooks y custom functions."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.config import get_settings
from app.deps.auth import require_user_id
from app.services.retell_agent_setup import ensure_retell_agent
from app.services.retell_client import get_retell_client, verify_retell_webhook
from app.services.voice_tool_executor import execute_voice_tool
from app.services.voice_usage import voice_access_state

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/retell", tags=["retell"])


class RegisterCallBody(BaseModel):
    user_id: str | None = Field(default=None, alias="userId")

    model_config = {"populate_by_name": True}


def _voice_access_or_raise(user_id: str) -> None:
    balance = voice_access_state(user_id)
    if balance.get("access_denied"):
        raise HTTPException(
            status_code=403,
            detail="Acceso de voz no disponible. Elige un plan en Precios.",
        )
    if balance.get("blocked"):
        raise HTTPException(
            status_code=429,
            detail="Alcanzaste tu límite diario de voz. Recarga o vuelve mañana.",
        )
    if balance.get("plan_minutes_daily", 0) <= 0 and balance.get("access_message") == "free_basic":
        raise HTTPException(
            status_code=403,
            detail="La voz no está incluida en el plan Básico gratis.",
        )


def _extract_user_id(payload: dict[str, Any]) -> str:
    call = payload.get("call") or {}
    metadata = call.get("metadata") or {}
    user_id = str(metadata.get("user_id") or metadata.get("userId") or "").strip()
    return user_id


async def _verify_retell_request(request: Request) -> dict[str, Any]:
    raw = (await request.body()).decode("utf-8")
    signature = request.headers.get("X-Retell-Signature")
    settings = get_settings()

    if settings.retell_webhook_secret.strip():
        secret = settings.retell_webhook_secret.strip()
        if signature != secret:
            raise HTTPException(status_code=401, detail="Unauthorized")
    elif settings.is_production():
        if not verify_retell_webhook(raw, signature):
            raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        return json.loads(raw) if raw else {}
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc


@router.post("/register-call")
async def register_retell_call(
    body: RegisterCallBody | None = None,
    user_id: str = Depends(require_user_id),
) -> dict[str, Any]:
    """Crea web call Retell y devuelve access_token para el SDK frontend."""
    settings = get_settings()
    if settings.voice_provider != "retell":
        raise HTTPException(status_code=503, detail="Proveedor de voz Retell no activo.")

    client = get_retell_client()
    if not client:
        raise HTTPException(status_code=503, detail="RETELL_API_KEY no configurada.")

    agent_id = settings.retell_agent_id.strip()
    if not agent_id:
        raise HTTPException(
            status_code=503,
            detail="RETELL_AGENT_ID no configurado. Ejecute setup_retell_agent.",
        )

    _voice_access_or_raise(user_id)

    try:
        call = client.call.create_web_call(
            agent_id=agent_id,
            metadata={"user_id": user_id},
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("[RETELL] create_web_call failed: %s", exc)
        raise HTTPException(status_code=502, detail="No pude iniciar llamada Retell.") from exc

    return {
        "ok": True,
        "access_token": call.access_token,
        "call_id": getattr(call, "call_id", None) or getattr(call, "callId", None),
        "agent_id": agent_id,
    }


@router.post("/webhook")
async def retell_webhook(request: Request) -> dict[str, Any]:
    """Eventos generales de llamada Retell (call_started, call_ended, etc.)."""
    payload = await _verify_retell_request(request)
    event = payload.get("event") or payload.get("event_type") or "unknown"
    logger.info("[RETELL] webhook event=%s", event)
    return {"received": True}


@router.post("/tools/{tool_name}")
async def retell_tool_handler(tool_name: str, request: Request) -> JSONResponse:
    """Custom function invocada por Retell durante la llamada."""
    payload = await _verify_retell_request(request)
    args = payload.get("args") or {}
    user_id = _extract_user_id(payload)

    if not user_id:
        logger.warning("[RETELL] tool=%s sin user_id en metadata", tool_name)
        return JSONResponse(
            status_code=200,
            content={"result": "No identifiqué al usuario, señor."},
        )

    result = await execute_voice_tool(tool_name, user_id, args)
    spoken = str(result.get("spoken") or "Completado, señor.")
    return JSONResponse(status_code=200, content={"result": spoken})


@router.get("/config")
async def retell_config(_user_id: str = Depends(require_user_id)) -> dict:
    settings = get_settings()
    return {
        "provider": settings.voice_provider,
        "agentConfigured": bool(settings.retell_agent_id.strip()),
        "voiceId": settings.retell_voice_id.strip() or "11labs-George",
    }


@router.post("/admin/bootstrap")
async def retell_bootstrap_agent(user_id: str = Depends(require_user_id)) -> dict[str, Any]:
    """Bootstrap manual del agente (admin/dev). Requiere usuario autenticado."""
    settings = get_settings()
    if not settings.retell_api_key.strip():
        raise HTTPException(status_code=503, detail="RETELL_API_KEY no configurada.")

    agent_id = settings.retell_agent_id.strip() or None
    llm_id = settings.retell_llm_id.strip() or None
    try:
        out = ensure_retell_agent(agent_id=agent_id, llm_id=llm_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("[RETELL] bootstrap failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {"ok": True, **out, "hint": "Guarde RETELL_AGENT_ID y RETELL_LLM_ID en Railway."}
