"""Retell AI — registro de llamadas, webhooks y custom functions."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import httpx

from app.config import get_settings
from app.deps.auth import require_super_admin, require_user_id
from app.services.retell_agent_cache import (
    get_last_bootstrap_error,
    get_last_bootstrap_info,
    get_last_native_staging_info,
    get_native_staging_agent_id,
    get_retell_agent_id,
)
from app.services.retell_agent_setup import (
    bootstrap_retell_if_needed,
    custom_llm_websocket_url,
    ensure_retell_agent,
)
from app.services.retell_ws_tracker import active_ws_calls
from app.services.retell_call_registry import bind_call_user, release_call_user, resolve_call_user
from app.services.retell_client import get_retell_client, verify_retell_webhook
from app.services.retell_native_pilot import (
    execute_activate_advanced_mode_tool,
    execute_activate_camera_tool,
    execute_analyze_camera_frame_tool,
    execute_consult_advanced_tool,
    execute_deactivate_advanced_mode_tool,
    execute_deactivate_camera_tool,
    execute_finance_cancel_write_tool,
    execute_finance_confirm_write_tool,
    execute_finance_prepare_write_tool,
    execute_get_environment_tool,
    execute_check_meta_networks_tool,
    execute_meta_cancel_publish_tool,
    execute_meta_confirm_publish_tool,
    execute_meta_prepare_publish_tool,
    execute_enable_prospection_tool,
    execute_disable_prospection_tool,
    execute_prospection_report_tool,
    execute_read_social_comments_tool,
    execute_open_drive_map_tool,
    execute_open_opportunities_tool,
    execute_play_youtube_video_tool,
    execute_pause_youtube_video_tool,
    execute_resume_youtube_video_tool,
    execute_close_youtube_player_tool,
    execute_generate_image_tool,
    execute_generar_pdf_tool,
    execute_search_nearby_places_tool,
    execute_show_route_tool,
    execute_start_drive_navigation_tool,
    execute_stop_drive_navigation_tool,
    execute_navigation_status_tool,
    execute_read_finances_tool,
    execute_search_visible_product_tool,
    execute_search_web_tool,
    get_call_pilot_metrics,
    get_pilot_metrics_snapshot,
)
from app.services.finance_write_flow import clear_finance_pending_for_call
from app.services.meta_publish_flow import clear_meta_pending_for_call
from app.services.voice_client_session import clear_advanced_mode_for_call
from app.services.retell_native_staging import bootstrap_native_staging_pilot, ensure_native_staging_agent
from app.services.voice_tool_executor import execute_voice_tool
from app.services.voice_usage import ACCESS_DENIED_MESSAGES, voice_access_state_async
from app.services import supabase_db
from app.services.async_sync import run_sync

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/retell", tags=["retell"])


class RegisterCallBody(BaseModel):
    user_id: str | None = Field(default=None, alias="userId")

    model_config = {"populate_by_name": True}


async def _voice_access_or_raise(user_id: str) -> None:
    await run_sync(supabase_db.start_voice_trial_clock, user_id)
    balance = await voice_access_state_async(user_id)
    msg = balance.get("access_message") or ""
    if balance.get("access_denied") or msg in (
        "trial_expired",
        "cierre_trial_expired",
    ):
        detail = ACCESS_DENIED_MESSAGES.get(msg, msg or "Acceso no disponible.")
        raise HTTPException(status_code=403, detail=detail)
    if balance.get("blocked"):
        if balance.get("quota_exhausted"):
            raise HTTPException(
                status_code=402,
                detail="Has alcanzado tu límite diario de voz. Recarga desde $10 o adquiere un plan. El chat sigue disponible.",
            )
        if msg == "past_due":
            raise HTTPException(
                status_code=402,
                detail=ACCESS_DENIED_MESSAGES["past_due"],
            )
        raise HTTPException(
            status_code=402,
            detail="La voz no está incluida sin plan activo o saldo. Mejora tu plan o recarga desde $10.",
        )


def _extract_user_id(payload: dict[str, Any]) -> str:
    call = payload.get("call") or {}
    metadata = call.get("metadata") or {}
    user_id = str(metadata.get("user_id") or metadata.get("userId") or "").strip()
    if user_id:
        return user_id
    call_id = str(call.get("call_id") or call.get("callId") or "").strip()
    if call_id:
        resolved = resolve_call_user(call_id, payload)
        if resolved:
            return resolved
    return ""


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


def _format_retell_call_error(exc: Exception) -> str:
    """Mensaje claro para el usuario según el error de Retell."""
    raw = str(exc).strip()
    lower = raw.lower()
    if "402" in lower or "payment required" in lower or "trial" in lower:
        return (
            "Cuenta Retell sin saldo o prueba expirada. "
            "Agregue método de pago en retellai.com."
        )
    if "401" in lower or "unauthorized" in lower:
        return "RETELL_API_KEY inválida. Revise la variable en Railway."
    if "422" in lower or "not found" in lower:
        return "Agente Retell no encontrado. Ejecute bootstrap del agente."
    if "429" in lower or "rate limit" in lower:
        return "Demasiadas llamadas. Espere unos segundos e intente de nuevo."
    if "language" in lower:
        return "Error de idioma en agente Retell — se está corrigiendo, intente en 1 minuto."
    if raw:
        snippet = raw if len(raw) <= 220 else f"{raw[:220]}…"
        return f"No pude iniciar llamada Retell: {snippet}"
    return "No pude iniciar llamada Retell."


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

    agent_id = get_retell_agent_id()
    if not agent_id:
        try:
            boot = await asyncio.to_thread(bootstrap_retell_if_needed)
            agent_id = (boot or {}).get("agent_id") or get_retell_agent_id()
        except Exception as exc:  # noqa: BLE001
            logger.warning("[RETELL] bootstrap on register failed: %s", exc)
    if not agent_id:
        err = get_last_bootstrap_error()
        raise HTTPException(
            status_code=503,
            detail=err or "RETELL_AGENT_ID no configurado. Reinicie API o ejecute bootstrap.",
        )

    await _voice_access_or_raise(user_id)

    try:
        await asyncio.to_thread(ensure_retell_agent, agent_id=agent_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[RETELL] agent refresh before call failed (continuing): %s", exc)

    try:
        call = await asyncio.to_thread(
            client.call.create_web_call,
            agent_id=agent_id,
            metadata={"user_id": user_id},
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("[RETELL] create_web_call failed: %s", exc)
        raise HTTPException(status_code=502, detail=_format_retell_call_error(exc)) from exc

    call_id = getattr(call, "call_id", None) or getattr(call, "callId", None)
    if call_id:
        bind_call_user(str(call_id), user_id)
        from app.services import voice_client_session as vcs

        vcs.begin_voice_publish_session(user_id, str(call_id))
        logger.info("[RETELL] voice publish session reset call=%s user=%s", call_id, user_id[:8])

    return {
        "ok": True,
        "access_token": call.access_token,
        "call_id": call_id,
        "agent_id": agent_id,
    }


@router.post("/register-call-native-pilot")
async def register_retell_native_pilot_call(
    body: RegisterCallBody | None = None,
    user_id: str = Depends(require_user_id),
) -> dict[str, Any]:
    """Web call contra el agente Retell LLM nativo de staging (piloto clima)."""
    settings = get_settings()
    if settings.voice_provider != "retell":
        raise HTTPException(status_code=503, detail="Proveedor de voz Retell no activo.")

    client = get_retell_client()
    if not client:
        raise HTTPException(status_code=503, detail="RETELL_API_KEY no configurada.")

    agent_id = get_native_staging_agent_id()
    if not agent_id:
        try:
            boot = await asyncio.to_thread(bootstrap_native_staging_pilot)
            agent_id = (boot or {}).get("agent_id") or get_native_staging_agent_id()
        except Exception as exc:  # noqa: BLE001
            logger.warning("[NATIVE-PILOT] bootstrap on register failed: %s", exc)
            raise HTTPException(
                status_code=503,
                detail=f"Piloto nativo no configurado: {exc}",
            ) from exc
    if not agent_id:
        raise HTTPException(
            status_code=503,
            detail="RETELL_NATIVE_STAGING_AGENT_ID no configurado. Ejecute bootstrap del piloto.",
        )

    await _voice_access_or_raise(user_id)

    creator_mode = "false"
    try:
        from app.deps.auth import is_super_admin
        from app.services import supabase_db

        profile = supabase_db.get_profile(user_id) or {}
        if is_super_admin(profile.get("email"), profile.get("role")):
            creator_mode = "true"
    except Exception:  # noqa: BLE001
        creator_mode = "false"

    try:
        await asyncio.to_thread(ensure_native_staging_agent, agent_id=agent_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[NATIVE-PILOT] agent refresh before call failed (continuing): %s", exc)

    try:
        call = await asyncio.to_thread(
            client.call.create_web_call,
            agent_id=agent_id,
            metadata={"user_id": user_id, "pilot": "native-llm-environment"},
            retell_llm_dynamic_variables={
                "user_id": user_id,
                "creator_mode": creator_mode,
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("[NATIVE-PILOT] create_web_call failed: %s", exc)
        raise HTTPException(status_code=502, detail=_format_retell_call_error(exc)) from exc

    call_id = getattr(call, "call_id", None) or getattr(call, "callId", None)
    if call_id:
        bind_call_user(str(call_id), user_id)
        from app.services import voice_client_session as vcs

        vcs.begin_voice_publish_session(user_id, str(call_id))
        logger.info("[NATIVE-PILOT] call=%s user=%s agent=%s", call_id, user_id[:8], agent_id[:12])

    staging_info = get_last_native_staging_info() or {}
    return {
        "ok": True,
        "access_token": call.access_token,
        "call_id": call_id,
        "agent_id": agent_id,
        "pilot": "native-llm-environment",
        "engine": "retell-llm",
        "model": staging_info.get("model") or settings.retell_native_pilot_model,
    }


@router.post("/tools/get_environment")
async def retell_get_environment_tool(request: Request) -> JSONResponse:
    """Custom function get_environment — piloto Retell LLM nativo."""
    payload = await _verify_retell_request(request)
    args = payload.get("args") or {}
    user_id = _extract_user_id(payload)
    result = await execute_get_environment_tool(user_id=user_id, payload=payload, args=args)
    return JSONResponse(status_code=200, content={"result": result["result"]})










@router.post("/tools/search_web")
async def retell_search_web_tool(request: Request) -> JSONResponse:
    """Búsqueda web general — piloto nativo."""
    payload = await _verify_retell_request(request)
    args = payload.get("args") or {}
    user_id = _extract_user_id(payload)
    result = await execute_search_web_tool(user_id=user_id, payload=payload, args=args)
    return JSONResponse(status_code=200, content={"result": result["result"]})


@router.post("/tools/analyze_product_viability")
async def retell_analyze_product_viability_tool(request: Request) -> JSONResponse:
    """Viabilidad de producto/servicio — solo piloto nativo + flag de módulo."""
    from app.services.viability_pilot.voice_tool import (
        execute_analyze_product_viability_tool,
    )

    payload = await _verify_retell_request(request)
    args = payload.get("args") or {}
    user_id = _extract_user_id(payload)
    result = await execute_analyze_product_viability_tool(
        user_id=user_id, payload=payload, args=args
    )
    return JSONResponse(status_code=200, content={"result": result["result"]})


@router.post("/tools/play_youtube_video")
async def retell_play_youtube_video_tool(request: Request) -> JSONResponse:
    """Busca y reproduce un video de YouTube — piloto nativo."""
    payload = await _verify_retell_request(request)
    args = payload.get("args") or {}
    user_id = _extract_user_id(payload)
    result = await execute_play_youtube_video_tool(
        user_id=user_id, payload=payload, args=args
    )
    return JSONResponse(status_code=200, content={"result": result["result"]})


@router.post("/tools/pause_youtube_video")
async def retell_pause_youtube_video_tool(request: Request) -> JSONResponse:
    """Pausa el video de YouTube — piloto nativo."""
    payload = await _verify_retell_request(request)
    args = payload.get("args") or {}
    user_id = _extract_user_id(payload)
    result = await execute_pause_youtube_video_tool(
        user_id=user_id, payload=payload, args=args
    )
    return JSONResponse(status_code=200, content={"result": result["result"]})


@router.post("/tools/resume_youtube_video")
async def retell_resume_youtube_video_tool(request: Request) -> JSONResponse:
    """Reanuda el video de YouTube — piloto nativo."""
    payload = await _verify_retell_request(request)
    args = payload.get("args") or {}
    user_id = _extract_user_id(payload)
    result = await execute_resume_youtube_video_tool(
        user_id=user_id, payload=payload, args=args
    )
    return JSONResponse(status_code=200, content={"result": result["result"]})


@router.post("/tools/close_youtube_player")
async def retell_close_youtube_player_tool(request: Request) -> JSONResponse:
    """Cierra el panel de YouTube — piloto nativo."""
    payload = await _verify_retell_request(request)
    args = payload.get("args") or {}
    user_id = _extract_user_id(payload)
    result = await execute_close_youtube_player_tool(
        user_id=user_id, payload=payload, args=args
    )
    return JSONResponse(status_code=200, content={"result": result["result"]})


@router.post("/tools/generate_image")
async def retell_generate_image_tool(request: Request) -> JSONResponse:
    """Genera imagen con IA — piloto nativo (preview en pantalla)."""
    payload = await _verify_retell_request(request)
    args = payload.get("args") or {}
    user_id = _extract_user_id(payload)
    result = await execute_generate_image_tool(
        user_id=user_id, payload=payload, args=args
    )
    return JSONResponse(status_code=200, content={"result": result["result"]})


@router.post("/tools/generar_pdf")
async def retell_generar_pdf_tool(request: Request) -> JSONResponse:
    """Genera PDF descargable — piloto nativo (historial)."""
    payload = await _verify_retell_request(request)
    args = payload.get("args") or {}
    user_id = _extract_user_id(payload)
    result = await execute_generar_pdf_tool(
        user_id=user_id, payload=payload, args=args
    )
    return JSONResponse(status_code=200, content={"result": result["result"]})


@router.post("/tools/check_meta_networks")
async def retell_check_meta_networks_tool(request: Request) -> JSONResponse:
    """Estado de conexión Meta — piloto nativo."""
    payload = await _verify_retell_request(request)
    args = payload.get("args") or {}
    user_id = _extract_user_id(payload)
    result = await execute_check_meta_networks_tool(
        user_id=user_id, payload=payload, args=args
    )
    return JSONResponse(status_code=200, content={"result": result["result"]})


@router.post("/tools/meta_prepare_publish")
async def retell_meta_prepare_publish_tool(request: Request) -> JSONResponse:
    """Prepara borrador de publicación FB/IG — no publica."""
    payload = await _verify_retell_request(request)
    args = payload.get("args") or {}
    user_id = _extract_user_id(payload)
    result = await execute_meta_prepare_publish_tool(
        user_id=user_id, payload=payload, args=args
    )
    return JSONResponse(status_code=200, content={"result": result["result"]})


@router.post("/tools/meta_confirm_publish")
async def retell_meta_confirm_publish_tool(request: Request) -> JSONResponse:
    """Publica tras confirmación verificada en transcript."""
    payload = await _verify_retell_request(request)
    args = payload.get("args") or {}
    user_id = _extract_user_id(payload)
    result = await execute_meta_confirm_publish_tool(
        user_id=user_id, payload=payload, args=args
    )
    return JSONResponse(status_code=200, content={"result": result["result"]})


@router.post("/tools/meta_cancel_publish")
async def retell_meta_cancel_publish_tool(request: Request) -> JSONResponse:
    """Cancela borrador de publicación pendiente."""
    payload = await _verify_retell_request(request)
    args = payload.get("args") or {}
    user_id = _extract_user_id(payload)
    result = await execute_meta_cancel_publish_tool(
        user_id=user_id, payload=payload, args=args
    )
    return JSONResponse(status_code=200, content={"result": result["result"]})


@router.post("/tools/enable_prospection")
async def retell_enable_prospection_tool(request: Request) -> JSONResponse:
    payload = await _verify_retell_request(request)
    user_id = _extract_user_id(payload)
    result = await execute_enable_prospection_tool(
        user_id=user_id, payload=payload, args=payload.get("args") or {}
    )
    return JSONResponse(status_code=200, content={"result": result["result"]})


@router.post("/tools/disable_prospection")
async def retell_disable_prospection_tool(request: Request) -> JSONResponse:
    payload = await _verify_retell_request(request)
    user_id = _extract_user_id(payload)
    result = await execute_disable_prospection_tool(
        user_id=user_id, payload=payload, args=payload.get("args") or {}
    )
    return JSONResponse(status_code=200, content={"result": result["result"]})


@router.post("/tools/prospection_report")
async def retell_prospection_report_tool(request: Request) -> JSONResponse:
    payload = await _verify_retell_request(request)
    user_id = _extract_user_id(payload)
    result = await execute_prospection_report_tool(
        user_id=user_id, payload=payload, args=payload.get("args") or {}
    )
    return JSONResponse(status_code=200, content={"result": result["result"]})


@router.post("/tools/read_social_comments")
async def retell_read_social_comments_tool(request: Request) -> JSONResponse:
    payload = await _verify_retell_request(request)
    args = payload.get("args") or {}
    user_id = _extract_user_id(payload)
    result = await execute_read_social_comments_tool(
        user_id=user_id, payload=payload, args=args
    )
    return JSONResponse(status_code=200, content={"result": result["result"]})


@router.post("/tools/open_drive_map")
async def retell_open_drive_map_tool(request: Request) -> JSONResponse:
    payload = await _verify_retell_request(request)
    user_id = _extract_user_id(payload)
    result = await execute_open_drive_map_tool(
        user_id=user_id, payload=payload, args=payload.get("args") or {}
    )
    return JSONResponse(status_code=200, content={"result": result["result"]})


@router.post("/tools/open_opportunities")
async def retell_open_opportunities_tool(request: Request) -> JSONResponse:
    payload = await _verify_retell_request(request)
    user_id = _extract_user_id(payload)
    result = await execute_open_opportunities_tool(
        user_id=user_id, payload=payload, args=payload.get("args") or {}
    )
    return JSONResponse(status_code=200, content={"result": result["result"]})


@router.post("/tools/search_nearby_places")
async def retell_search_nearby_places_tool(request: Request) -> JSONResponse:
    payload = await _verify_retell_request(request)
    args = payload.get("args") or {}
    user_id = _extract_user_id(payload)
    result = await execute_search_nearby_places_tool(
        user_id=user_id, payload=payload, args=args
    )
    return JSONResponse(status_code=200, content={"result": result["result"]})


@router.post("/tools/show_route")
async def retell_show_route_tool(request: Request) -> JSONResponse:
    payload = await _verify_retell_request(request)
    args = payload.get("args") or {}
    user_id = _extract_user_id(payload)
    result = await execute_show_route_tool(user_id=user_id, payload=payload, args=args)
    return JSONResponse(status_code=200, content={"result": result["result"]})


@router.post("/tools/start_drive_navigation")
async def retell_start_drive_navigation_tool(request: Request) -> JSONResponse:
    payload = await _verify_retell_request(request)
    user_id = _extract_user_id(payload)
    result = await execute_start_drive_navigation_tool(
        user_id=user_id, payload=payload, args=payload.get("args") or {}
    )
    return JSONResponse(status_code=200, content={"result": result["result"]})


@router.post("/tools/stop_drive_navigation")
async def retell_stop_drive_navigation_tool(request: Request) -> JSONResponse:
    payload = await _verify_retell_request(request)
    user_id = _extract_user_id(payload)
    result = await execute_stop_drive_navigation_tool(
        user_id=user_id, payload=payload, args=payload.get("args") or {}
    )
    return JSONResponse(status_code=200, content={"result": result["result"]})


@router.post("/tools/navigation_status")
async def retell_navigation_status_tool(request: Request) -> JSONResponse:
    payload = await _verify_retell_request(request)
    user_id = _extract_user_id(payload)
    result = await execute_navigation_status_tool(
        user_id=user_id, payload=payload, args=payload.get("args") or {}
    )
    return JSONResponse(status_code=200, content={"result": result["result"]})


@router.post("/tools/read_finances")
async def retell_read_finances_tool(request: Request) -> JSONResponse:
    """Custom function read_finances — piloto nativo."""
    payload = await _verify_retell_request(request)
    args = payload.get("args") or {}
    user_id = _extract_user_id(payload)
    result = await execute_read_finances_tool(user_id=user_id, payload=payload, args=args)
    return JSONResponse(status_code=200, content={"result": result["result"]})


@router.post("/tools/finance_prepare_write")
async def retell_finance_prepare_write_tool(request: Request) -> JSONResponse:
    """Prepara borrador financiero — no guarda (piloto nativo)."""
    payload = await _verify_retell_request(request)
    args = payload.get("args") or {}
    user_id = _extract_user_id(payload)
    result = await execute_finance_prepare_write_tool(user_id=user_id, payload=payload, args=args)
    return JSONResponse(status_code=200, content={"result": result["result"]})


@router.post("/tools/finance_confirm_write")
async def retell_finance_confirm_write_tool(request: Request) -> JSONResponse:
    """Registra movimiento financiero tras confirmación verificada en transcript."""
    payload = await _verify_retell_request(request)
    args = payload.get("args") or {}
    user_id = _extract_user_id(payload)
    result = await execute_finance_confirm_write_tool(user_id=user_id, payload=payload, args=args)
    return JSONResponse(status_code=200, content={"result": result["result"]})


@router.post("/tools/activate_camera")
async def retell_activate_camera_tool(request: Request) -> JSONResponse:
    """Activa la cámara del cliente (piloto nativo) — idempotente."""
    payload = await _verify_retell_request(request)
    args = payload.get("args") or {}
    user_id = _extract_user_id(payload)
    result = await execute_activate_camera_tool(user_id=user_id, payload=payload, args=args)
    return JSONResponse(status_code=200, content={"result": result["result"]})


@router.post("/tools/deactivate_camera")
async def retell_deactivate_camera_tool(request: Request) -> JSONResponse:
    """Apaga la cámara del cliente (piloto nativo)."""
    payload = await _verify_retell_request(request)
    args = payload.get("args") or {}
    user_id = _extract_user_id(payload)
    result = await execute_deactivate_camera_tool(user_id=user_id, payload=payload, args=args)
    return JSONResponse(status_code=200, content={"result": result["result"]})


@router.post("/tools/analyze_camera_frame")
async def retell_analyze_camera_frame_tool(request: Request) -> JSONResponse:
    """Captura y analiza un frame de la cámara (piloto nativo)."""
    payload = await _verify_retell_request(request)
    args = payload.get("args") or {}
    user_id = _extract_user_id(payload)
    result = await execute_analyze_camera_frame_tool(
        user_id=user_id, payload=payload, args=args
    )
    return JSONResponse(status_code=200, content={"result": result["result"]})


@router.post("/tools/search_visible_product")
async def retell_search_visible_product_tool(request: Request) -> JSONResponse:
    """Identifica objeto visible y busca datos de producto (piloto nativo)."""
    payload = await _verify_retell_request(request)
    args = payload.get("args") or {}
    user_id = _extract_user_id(payload)
    result = await execute_search_visible_product_tool(
        user_id=user_id, payload=payload, args=args
    )
    return JSONResponse(status_code=200, content={"result": result["result"]})


@router.post("/tools/activate_advanced_mode")
async def retell_activate_advanced_mode_tool(request: Request) -> JSONResponse:
    """Activa modo avanzado Claude (piloto nativo)."""
    payload = await _verify_retell_request(request)
    args = payload.get("args") or {}
    user_id = _extract_user_id(payload)
    result = await execute_activate_advanced_mode_tool(
        user_id=user_id, payload=payload, args=args
    )
    return JSONResponse(status_code=200, content={"result": result["result"]})


@router.post("/tools/consult_advanced")
async def retell_consult_advanced_tool(request: Request) -> JSONResponse:
    """Consulta profunda Claude en modo avanzado (piloto nativo)."""
    payload = await _verify_retell_request(request)
    args = payload.get("args") or {}
    user_id = _extract_user_id(payload)
    result = await execute_consult_advanced_tool(
        user_id=user_id, payload=payload, args=args
    )
    return JSONResponse(status_code=200, content={"result": result["result"]})


@router.post("/tools/deactivate_advanced_mode")
async def retell_deactivate_advanced_mode_tool(request: Request) -> JSONResponse:
    """Sale del modo avanzado (piloto nativo)."""
    payload = await _verify_retell_request(request)
    args = payload.get("args") or {}
    user_id = _extract_user_id(payload)
    result = await execute_deactivate_advanced_mode_tool(
        user_id=user_id, payload=payload, args=args
    )
    return JSONResponse(status_code=200, content={"result": result["result"]})


@router.post("/tools/finance_cancel_write")
async def retell_finance_cancel_write_tool(request: Request) -> JSONResponse:
    """Cancela borrador financiero pendiente."""
    payload = await _verify_retell_request(request)
    args = payload.get("args") or {}
    user_id = _extract_user_id(payload)
    result = await execute_finance_cancel_write_tool(user_id=user_id, payload=payload, args=args)
    return JSONResponse(status_code=200, content={"result": result["result"]})


@router.post("/native-pilot/bootstrap")
async def retell_native_pilot_bootstrap(
    x_bootstrap_secret: str | None = Header(default=None, alias="X-Bootstrap-Secret"),
) -> dict[str, Any]:
    """Crea/actualiza agente staging Retell LLM nativo — no toca producción."""
    _verify_bootstrap_secret(x_bootstrap_secret)
    try:
        out = await asyncio.to_thread(bootstrap_native_staging_pilot)
    except Exception as exc:  # noqa: BLE001
        logger.exception("[NATIVE-PILOT] bootstrap failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "ok": True,
        **out,
        "hint": (
            "Copie RETELL_NATIVE_STAGING_AGENT_ID y RETELL_NATIVE_STAGING_LLM_ID a Railway. "
            "Producción (RETELL_AGENT_ID) no fue modificada."
        ),
    }



@router.get("/native-pilot/status")
async def retell_native_pilot_status(
    _user_id: str = Depends(require_user_id),
) -> dict[str, Any]:
    settings = get_settings()
    staging_id = get_native_staging_agent_id()
    prod_id = get_retell_agent_id()
    staging_info = get_last_native_staging_info() or {}
    client = get_retell_client()
    staging_agent: dict[str, Any] | None = None
    if client and staging_id:
        try:
            agent = client.agent.retrieve(agent_id=staging_id)
            staging_agent = _json_safe(
                {
                    "agent_id": getattr(agent, "agent_id", staging_id),
                    "agent_name": getattr(agent, "agent_name", None),
                    "voice_id": getattr(agent, "voice_id", None),
                    "response_engine": getattr(agent, "response_engine", None),
                }
            )
        except Exception as exc:  # noqa: BLE001
            staging_agent = {"error": str(exc)}

    return {
        "ok": True,
        "pilot": "native-llm-environment",
        "production_agent_id": prod_id or None,
        "staging_agent_id": staging_id or None,
        "staging_llm_id": settings.retell_native_staging_llm_id.strip() or staging_info.get("llm_id"),
        "model": settings.retell_native_pilot_model,
        "staging_agent": staging_agent,
        "metrics": get_pilot_metrics_snapshot(),
        "access": {
            "url_param": "?voicePilot=native",
            "register_endpoint": "/v1/retell/register-call-native-pilot",
        },
    }


@router.get("/native-pilot/metrics")
async def retell_native_pilot_metrics(
    _user_id: str = Depends(require_user_id),
) -> dict[str, Any]:
    return {"ok": True, **get_pilot_metrics_snapshot()}


@router.get("/native-pilot/call-metrics/{call_id}")
async def retell_native_pilot_call_metrics(
    call_id: str,
    _user_id: str = Depends(require_user_id),
) -> dict[str, Any]:
    local = get_call_pilot_metrics(call_id)
    out: dict[str, Any] = {"ok": True, "call_id": call_id, "local_metrics": local}

    client = get_retell_client()
    if client:
        try:
            call = await asyncio.to_thread(client.call.retrieve, call_id=call_id.strip())
            out["retell"] = _json_safe(
                {
                    "call_status": getattr(call, "call_status", None),
                    "disconnection_reason": getattr(call, "disconnection_reason", None),
                    "agent_id": getattr(call, "agent_id", None),
                    "llm_token_usage": getattr(call, "llm_token_usage", None),
                    "transcript": getattr(call, "transcript_object", None),
                    "start_timestamp": getattr(call, "start_timestamp", None),
                    "end_timestamp": getattr(call, "end_timestamp", None),
                }
            )
        except Exception as exc:  # noqa: BLE001
            out["retell_error"] = str(exc)

    return out


@router.post("/webhook")
async def retell_webhook(request: Request) -> dict[str, Any]:
    """Eventos generales de llamada Retell (call_started, call_ended, etc.)."""
    payload = await _verify_retell_request(request)
    event = payload.get("event") or payload.get("event_type") or "unknown"
    call = payload.get("call") or payload.get("data") or {}
    call_id = call.get("call_id") or call.get("callId")
    logger.info(
        "[RETELL] webhook event=%s call_id=%s status=%s",
        event,
        call_id,
        call.get("call_status") or call.get("status"),
    )
    if event == "call_ended" and call_id:
        uid = resolve_call_user(str(call_id), payload)
        if uid:
            clear_finance_pending_for_call(uid, str(call_id))
            clear_meta_pending_for_call(uid, str(call_id))
            clear_advanced_mode_for_call(uid, str(call_id))
        try:
            client = get_retell_client()
            if client:
                detail = client.call.retrieve(call_id=str(call_id))
                logger.info(
                    "[RETELL] call_ended id=%s disconnection=%s transcript_len=%s",
                    call_id,
                    getattr(detail, "disconnection_reason", None),
                    len(getattr(detail, "transcript_object", None) or []),
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[RETELL] call retrieve failed: %s", exc)
    return {"received": True}


@router.post("/tools/{tool_name}")
async def retell_tool_handler(tool_name: str, request: Request) -> JSONResponse:
    """Custom function invocada por Retell durante la llamada."""
    import asyncio

    payload = await _verify_retell_request(request)
    args = payload.get("args") or {}
    user_id = _extract_user_id(payload)

    if not user_id:
        logger.warning("[RETELL] tool=%s sin user_id en metadata", tool_name)
        return JSONResponse(
            status_code=200,
            content={"result": "No identifiqué al usuario, señor."},
        )

    publish_tools = {"publicar_facebook", "publicar_instagram"}
    timeout_sec = 30.0 if tool_name in publish_tools else 45.0
    try:
        result = await asyncio.wait_for(
            execute_voice_tool(tool_name, user_id, args),
            timeout=timeout_sec,
        )
    except asyncio.TimeoutError:
        logger.error("[PUBLISH] timeout retell webhook tool=%s user=%s", tool_name, user_id[:8])
        spoken = (
            "Señor, la publicación está tardando más de lo normal. "
            "¿Desea que lo intente de nuevo?"
            if tool_name in publish_tools
            else "La acción tardó demasiado, señor. ¿Reintentamos?"
        )
        return JSONResponse(status_code=200, content={"result": spoken})
    spoken = str(result.get("spoken") or "Completado, señor.")
    return JSONResponse(status_code=200, content={"result": spoken})


@router.get("/config")
async def retell_config(_user_id: str = Depends(require_user_id)) -> dict:
    settings = get_settings()
    agent_id = get_retell_agent_id()
    return {
        "provider": settings.voice_provider,
        "agentConfigured": bool(agent_id),
        "agentId": agent_id or None,
        "voiceId": settings.retell_voice_id.strip() or "11labs-George",
        "brain": settings.gemini_voice_model,
        "architecture": "retell-gpt41mini-cartesia",
    }


def _verify_bootstrap_secret(provided: str | None) -> None:
    settings = get_settings()
    expected = settings.retell_bootstrap_secret.strip() or settings.retell_api_key.strip()
    if not expected:
        raise HTTPException(status_code=503, detail="Bootstrap no configurado en servidor.")
    if not provided or provided.strip() != expected:
        raise HTTPException(status_code=401, detail="Secret inválido.")


@router.post("/bootstrap-public")
async def retell_bootstrap_public(
    x_bootstrap_secret: str | None = Header(default=None, alias="X-Bootstrap-Secret"),
) -> dict[str, Any]:
    """Bootstrap sin auth de usuario — requiere X-Bootstrap-Secret (= RETELL_API_KEY o RETELL_BOOTSTRAP_SECRET)."""
    _verify_bootstrap_secret(x_bootstrap_secret)
    if not get_settings().google_api_key.strip():
        raise HTTPException(status_code=503, detail="GOOGLE_API_KEY no configurada.")

    agent_id = get_retell_agent_id() or None
    try:
        out = bootstrap_retell_if_needed() or ensure_retell_agent(agent_id=agent_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("[RETELL] bootstrap-public failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {
        "ok": True,
        **out,
        "hint": "Copie RETELL_AGENT_ID a Railway y redeploy para persistir.",
    }


@router.get("/bootstrap-status")
async def retell_bootstrap_status(
    x_bootstrap_secret: str | None = Header(default=None, alias="X-Bootstrap-Secret"),
) -> dict[str, Any]:
    _verify_bootstrap_secret(x_bootstrap_secret)
    info = get_last_bootstrap_info() or {}
    agent_id = get_retell_agent_id()
    return {
        "ok": True,
        "agent_id": agent_id or info.get("agent_id"),
        "voice_id": info.get("voice_id") or get_settings().retell_voice_id or "11labs-George",
        "llm_websocket_url": info.get("llm_websocket_url"),
        "brain": info.get("brain") or get_settings().gemini_voice_model,
    }


@router.get("/ideogram-probe")
async def retell_ideogram_probe(
    x_bootstrap_secret: str | None = Header(default=None, alias="X-Bootstrap-Secret"),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Diagnóstico Ideogram — confirma IDEOGRAM_API_KEY configurada y respuesta real
    de la API. Acepta X-Bootstrap-Secret O un JWT de super admin. No consume
    cupo/monedero de usuario (llama directo al servicio, sin pasar por generate_image())."""
    settings = get_settings()
    expected_secret = settings.retell_bootstrap_secret.strip() or settings.retell_api_key.strip()
    secret_ok = bool(expected_secret) and bool(x_bootstrap_secret) and x_bootstrap_secret.strip() == expected_secret
    if not secret_ok:
        from app.deps.auth import is_super_admin, require_auth_user

        user = await require_auth_user(authorization)
        if not is_super_admin(user.get("email"), user.get("role")):
            raise HTTPException(status_code=401, detail="Secret inválido o cuenta no es super admin.")
    has_key = bool(settings.ideogram_api_key.strip())
    if not has_key:
        return {"ok": False, "has_api_key": False, "error": "IDEOGRAM_API_KEY no configurada"}

    from app.services.ideogram_images import generate_image_ideogram

    result = await asyncio.to_thread(
        generate_image_ideogram,
        prompt='Un cartel simple que diga "PRUEBA"',
    )
    return {
        "has_api_key": True,
        "ok": result.get("ok"),
        "error": result.get("error"),
        "code": result.get("code"),
        "bytes": len(result.get("raw_bytes") or b"") if result.get("ok") else 0,
        "rendering_speed": result.get("rendering_speed") or settings.ideogram_rendering_speed,
        "resolution": settings.ideogram_resolution,
        "num_images_requested": result.get("num_images_requested"),
        "num_images_returned": result.get("num_images_returned"),
        "estimated_cost_usd": result.get("estimated_cost_usd"),
        "provider_request_cost_usd": result.get("provider_request_cost_usd"),
        "wallet_unit_cost_usd": result.get("wallet_unit_cost_usd"),
        "model": result.get("model"),
    }


@router.get("/bootstrap-now")
async def retell_bootstrap_now(
    voice_id: str | None = None,
    _admin_id: str = Depends(require_super_admin),
) -> dict[str, Any]:
    """Bootstrap Retell — solo super admin."""
    settings = get_settings()
    if not settings.retell_api_key.strip():
        return {"ok": False, "error": "RETELL_API_KEY vacía en Railway"}
    if not settings.google_api_key.strip():
        return {"ok": False, "error": "GOOGLE_API_KEY vacía en Railway"}

    from app.services.retell_agent_cache import set_bootstrapped_agent, set_bootstrap_error

    existing = get_retell_agent_id() or None
    try:
        result = ensure_retell_agent(agent_id=existing, voice_id_override=voice_id)
        set_bootstrapped_agent(result["agent_id"], result)
        return {
            "ok": True,
            **result,
            "message": "Copie RETELL_AGENT_ID a Railway para persistir tras reinicios.",
        }
    except Exception as exc:  # noqa: BLE001
        err = str(exc)
        set_bootstrap_error(err)
        logger.exception("[RETELL] bootstrap-now failed")
        return {"ok": False, "error": err, "api_public_url": settings.api_public_url}


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if hasattr(value, "model_dump"):
        return _json_safe(value.model_dump())
    return str(value)


@router.get("/call-debug/{call_id}")
async def retell_call_debug(
    call_id: str,
    _admin_id: str = Depends(require_super_admin),
) -> dict[str, Any]:
    """Estado de una llamada Retell — solo super admin (transcript/recording)."""
    client = get_retell_client()
    if not client:
        return {"ok": False, "error": "RETELL_API_KEY no configurada"}

    try:
        call = await asyncio.to_thread(client.call.retrieve, call_id=call_id.strip())
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "call_id": call_id}

    transcript = getattr(call, "transcript_object", None) or getattr(call, "transcript", None) or []
    return _json_safe(
        {
            "ok": True,
            "call_id": getattr(call, "call_id", call_id),
            "call_status": getattr(call, "call_status", None),
            "disconnection_reason": getattr(call, "disconnection_reason", None),
            "agent_id": getattr(call, "agent_id", None),
            "transcript": transcript,
            "llm_token_usage": getattr(call, "llm_token_usage", None),
            "recording_url": getattr(call, "recording_url", None),
            "start_timestamp": getattr(call, "start_timestamp", None),
            "end_timestamp": getattr(call, "end_timestamp", None),
            "expected_llm_ws_url": f"{custom_llm_websocket_url()}/{call_id.strip()}",
            "active_llm_ws": active_ws_calls(),
        }
    )


@router.get("/diagnostics")
async def retell_diagnostics(
    _admin_id: str = Depends(require_super_admin),
) -> dict[str, Any]:
    """Diagnóstico voz — solo super admin."""
    settings = get_settings()
    out: dict[str, Any] = {
        "ok": True,
        "voice_provider": settings.voice_provider,
        "has_retell_api_key": bool(settings.retell_api_key.strip()),
        "has_google_api_key": bool(settings.google_api_key.strip()),
        "has_elevenlabs_api_key": bool(settings.elevenlabs_api_key.strip()),
        "agent_id": get_retell_agent_id(),
        "llm_websocket_url": custom_llm_websocket_url(),
        "llm_websocket_url_note": "Retell añade /{call_id} al final — no usar placeholder {call_id} en la URL base",
        "active_llm_ws": active_ws_calls(),
    }

    client = get_retell_client()
    if not client:
        out["ok"] = False
        out["error"] = "RETELL_API_KEY no configurada"
        return out

    agent_id = get_retell_agent_id() or settings.retell_agent_id.strip()
    if agent_id:
        try:
            agent = client.agent.retrieve(agent_id=agent_id)
            out["agent"] = _json_safe(
                {
                    "agent_id": getattr(agent, "agent_id", agent_id),
                    "voice_id": getattr(agent, "voice_id", None),
                    "response_engine": getattr(agent, "response_engine", None),
                    "language": getattr(agent, "language", None),
                }
            )
        except Exception as exc:  # noqa: BLE001
            out["agent_error"] = str(exc)

    try:
        listed = client.voice.list()
        voices = getattr(listed, "voices", None) or listed
        ids = []
        for voice in voices or []:
            vid = getattr(voice, "voice_id", None) or (
                voice.get("voice_id") if isinstance(voice, dict) else None
            )
            if vid:
                ids.append(str(vid))
        out["retell_voices_count"] = len(ids)
        out["retell_voices_sample"] = ids[:20]
        out["openai_voices"] = [v for v in ids if v.startswith("openai-")]
        out["elevenlabs_voices"] = [v for v in ids if v.startswith("11labs-")]
    except Exception as exc:  # noqa: BLE001
        out["voices_error"] = str(exc)

    if settings.elevenlabs_api_key.strip():
        try:
            import httpx

            with httpx.Client(timeout=12.0) as http:
                res = http.get(
                    "https://api.elevenlabs.io/v1/user",
                    headers={"xi-api-key": settings.elevenlabs_api_key.strip()},
                )
                out["elevenlabs_user_status"] = res.status_code
                if res.status_code == 200:
                    data = res.json()
                    sub = data.get("subscription") or {}
                    out["elevenlabs"] = {
                        "tier": sub.get("tier"),
                        "character_count": sub.get("character_count"),
                        "character_limit": sub.get("character_limit"),
                    }
                else:
                    out["elevenlabs_error"] = res.text[:200]
        except Exception as exc:  # noqa: BLE001
            out["elevenlabs_error"] = str(exc)

    try:
        from google import genai
        from google.genai import types

        gemini = genai.Client(api_key=settings.google_api_key.strip())
        model = settings.gemini_voice_model.strip() or "gemini-2.5-pro"
        response = await gemini.aio.models.generate_content(
            model=model,
            contents=[types.Content(role="user", parts=[types.Part(text="Di hola en una palabra.")])],
        )
        text = (response.text or "").strip()
        out["gemini_ok"] = bool(text)
        out["gemini_sample"] = text[:80]
    except Exception as exc:  # noqa: BLE001
        out["gemini_ok"] = False
        out["gemini_error"] = str(exc)

    return out


@router.get("/jarvis-voice")
async def retell_jarvis_voice_setup(
    _admin_id: str = Depends(require_super_admin),
) -> dict[str, Any]:
    """Registrar clon Jarvis — solo super admin."""
    settings = get_settings()
    client = get_retell_client()
    if not client:
        return {"ok": False, "error": "RETELL_API_KEY no configurada"}

    from app.services.retell_agent_setup import (
        JARVIS_CLONED_ELEVENLABS_ID,
        ensure_jarvis_voice_in_retell,
        find_retell_voice_by_elevenlabs_id,
        find_voice_by_id,
        search_jarvis_voices,
        _normalize_voice_id,
        list_custom_voices,
    )

    el_id = settings.elevenlabs_jarvis_voice_id.strip() or JARVIS_CLONED_ELEVENLABS_ID
    configured = _normalize_voice_id(settings.retell_voice_id)
    mapped = find_retell_voice_by_elevenlabs_id(client, configured or el_id)
    retell_id, err = ensure_jarvis_voice_in_retell(client)
    agent_voice_id: str | None = None
    native_voice_id: str | None = None
    agent_ref = get_retell_agent_id() or settings.retell_agent_id.strip()
    if agent_ref:
        try:
            agent_voice_id = str(getattr(client.agent.retrieve(agent_id=agent_ref), "voice_id", "") or "") or None
        except Exception:  # noqa: BLE001
            pass
    native_ref = get_native_staging_agent_id() or settings.retell_native_staging_agent_id.strip()
    if native_ref:
        try:
            native_voice_id = (
                str(getattr(client.agent.retrieve(agent_id=native_ref), "voice_id", "") or "") or None
            )
        except Exception:  # noqa: BLE001
            pass

    active_voice_id = native_voice_id or agent_voice_id
    active_voice = find_voice_by_id(client, active_voice_id or "") if active_voice_id else None

    return {
        "ok": bool(mapped or retell_id or (agent_voice_id and agent_voice_id != "11labs-Brian")),
        "elevenlabs_voice_id": el_id,
        "configured_retell_voice_id": configured or None,
        "retell_voice_id_from_library": mapped,
        "retell_voice_id": mapped or retell_id,
        "agent_voice_id": agent_voice_id,
        "native_pilot_agent_id": native_ref or None,
        "native_pilot_voice_id": native_voice_id,
        "active_voice": active_voice,
        "tts_billing_hint": {
            "elevenlabs": 0.040,
            "platform": 0.015,
            "cartesia": 0.015,
            "minimax": 0.015,
            "fish_audio": 0.015,
            "openai": 0.015,
            "retell": 0.015,
        },
        "jarvis_voice_matches": search_jarvis_voices(client, query=configured or el_id),
        "custom_voices": list_custom_voices(client),
        "error": err,
        "hint": (
            "RETELL_VOICE_ID debe ser el ID de Retell (ej. custom-xxx), NO el de ElevenLabs. "
            "En Retell dashboard → Voices → copie el voice_id de su clon Jarvis."
        ),
    }


@router.get("/voice-raw-debug")
async def retell_voice_raw_debug(
    _admin_id: str = Depends(require_super_admin),
) -> dict[str, Any]:
    """Diagnóstico de solo lectura — solo super admin.

    NUNCA modifica agente ni voces.

    Vuelca los objetos crudos que devuelve la API de Retell para las voces
    custom_voice_* candidatas y para el voice_id actualmente asignado a los
    agentes de producción/piloto, con TODOS los campos que expone el SDK
    (para buscar metadata de creación/actualización, no solo voice_id/name).
    También hace un retrieve fresco (sin caché) de ambos agentes.
    """
    from app.services.retell_agent_setup import _list_retell_voices, _voice_field

    client = get_retell_client()
    if not client:
        return {"ok": False, "error": "RETELL_API_KEY no configurada"}

    def _raw_voice_dump(voice: Any) -> dict[str, Any]:
        if isinstance(voice, dict):
            return _json_safe(voice)
        if hasattr(voice, "model_dump"):
            return _json_safe(voice.model_dump())
        return {
            k: _json_safe(getattr(voice, k))
            for k in dir(voice)
            if not k.startswith("_") and not callable(getattr(voice, k, None))
        }

    all_voices = _list_retell_voices(client)
    voices_by_id = {_voice_field(v, "voice_id"): v for v in all_voices}

    watch_ids = [
        "custom_voice_8b067b589132b1ae5a05e2e4b0",
        "custom_voice_40933c7909bce8f877746d0638",
    ]
    voice_dumps: dict[str, Any] = {}
    for vid in watch_ids:
        v = voices_by_id.get(vid)
        voice_dumps[vid] = _raw_voice_dump(v) if v is not None else {"error": "not found in voice.list()"}

    all_custom_voices_raw = [
        _raw_voice_dump(v)
        for v in all_voices
        if _voice_field(v, "voice_id").startswith("custom_voice_")
    ]

    agent_dumps: dict[str, Any] = {}
    prod_id = get_retell_agent_id()
    native_id = get_native_staging_agent_id()
    for label, agent_id in (("production", prod_id), ("native_pilot", native_id)):
        if not agent_id:
            agent_dumps[label] = {"error": "no agent_id configured"}
            continue
        try:
            agent = client.agent.retrieve(agent_id=agent_id)
            agent_dumps[label] = {
                "agent_id": agent_id,
                "fresh_voice_id": getattr(agent, "voice_id", None),
                "voice_model": getattr(agent, "voice_model", None),
                "voice_speed": getattr(agent, "voice_speed", None),
                "voice_temperature": getattr(agent, "voice_temperature", None),
                "last_modification_timestamp": getattr(
                    agent, "last_modification_timestamp", None
                ),
            }
        except Exception as exc:  # noqa: BLE001
            agent_dumps[label] = {"error": str(exc)}

    return {
        "ok": True,
        "note": "Solo lectura — no se modificó ningún agente ni voz.",
        "agents_fresh_retrieve": agent_dumps,
        "watch_voice_ids_raw": voice_dumps,
        "all_custom_voices_raw": all_custom_voices_raw,
    }


@router.get("/warmup")
async def retell_warmup() -> dict[str, Any]:
    """Despierta la API sin bootstrap pesado — precalentamiento al cargar la web."""
    return {
        "ok": True,
        "agent_configured": bool(get_retell_agent_id()),
    }


@router.get("/status")
async def retell_public_status() -> dict[str, Any]:
    """Estado Retell mínimo sin auth (sin IDs internos ni URLs de LLM)."""
    settings = get_settings()
    agent_id = get_retell_agent_id()
    return {
        "ok": True,
        "voice_provider": settings.voice_provider,
        "agent_configured": bool(agent_id),
    }


@router.post("/admin/bootstrap")
async def retell_bootstrap_agent(
    _admin_id: str = Depends(require_super_admin),
) -> dict[str, Any]:
    """Bootstrap manual del agente — solo super admin."""
    settings = get_settings()
    if not settings.retell_api_key.strip():
        raise HTTPException(status_code=503, detail="RETELL_API_KEY no configurada.")

    agent_id = settings.retell_agent_id.strip() or None
    try:
        out = bootstrap_retell_if_needed() or ensure_retell_agent(agent_id=agent_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("[RETELL] bootstrap failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {
        "ok": True,
        **out,
        "hint": "Guarde RETELL_AGENT_ID y RETELL_VOICE_ID en Railway.",
    }
