"""Retell AI — registro de llamadas, webhooks y custom functions."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.config import get_settings
from app.deps.auth import require_user_id
from app.services.retell_agent_cache import get_last_bootstrap_error, get_last_bootstrap_info, get_retell_agent_id
from app.services.retell_agent_setup import (
    bootstrap_retell_if_needed,
    custom_llm_websocket_url,
    ensure_retell_agent,
)
from app.services.retell_ws_tracker import active_ws_calls
from app.services.retell_call_registry import bind_call_user, release_call_user, resolve_call_user
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

    agent_id = get_retell_agent_id()
    if not agent_id:
        raise HTTPException(
            status_code=503,
            detail="RETELL_AGENT_ID no configurado. Reinicie API o ejecute bootstrap.",
        )

    _voice_access_or_raise(user_id)

    try:
        # create_web_call es síncrono: liberar event loop para que Retell abra el LLM WS.
        call = await asyncio.to_thread(
            client.call.create_web_call,
            agent_id=agent_id,
            metadata={"user_id": user_id},
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("[RETELL] create_web_call failed: %s", exc)
        raise HTTPException(status_code=502, detail="No pude iniciar llamada Retell.") from exc

    call_id = getattr(call, "call_id", None) or getattr(call, "callId", None)
    if call_id:
        bind_call_user(str(call_id), user_id)

    return {
        "ok": True,
        "access_token": call.access_token,
        "call_id": call_id,
        "agent_id": agent_id,
    }


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
    agent_id = get_retell_agent_id()
    return {
        "provider": settings.voice_provider,
        "agentConfigured": bool(agent_id),
        "agentId": agent_id or None,
        "voiceId": settings.retell_voice_id.strip() or "11labs-George",
        "brain": settings.gemini_voice_model,
        "architecture": "retell-gemini-elevenlabs",
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


@router.get("/bootstrap-now")
async def retell_bootstrap_now() -> dict[str, Any]:
    """Ejecuta bootstrap Retell sin auth — devuelve agent_id o error exacto."""
    settings = get_settings()
    if not settings.retell_api_key.strip():
        return {"ok": False, "error": "RETELL_API_KEY vacía en Railway"}
    if not settings.google_api_key.strip():
        return {"ok": False, "error": "GOOGLE_API_KEY vacía en Railway"}

    from app.services.retell_agent_cache import set_bootstrapped_agent, set_bootstrap_error

    existing = get_retell_agent_id() or None
    try:
        result = ensure_retell_agent(agent_id=existing)
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
async def retell_call_debug(call_id: str) -> dict[str, Any]:
    """Estado de una llamada Retell (transcript, desconexión) — diagnóstico."""
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
async def retell_diagnostics() -> dict[str, Any]:
    """Diagnóstico voz: agente Retell, voces disponibles, Gemini ping."""
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
async def retell_jarvis_voice_setup() -> dict[str, Any]:
    """Intenta registrar el clon Jarvis y devuelve error detallado si falla."""
    settings = get_settings()
    client = get_retell_client()
    if not client:
        return {"ok": False, "error": "RETELL_API_KEY no configurada"}

    from app.services.retell_agent_setup import (
        JARVIS_CLONED_ELEVENLABS_ID,
        ensure_jarvis_voice_in_retell,
        find_retell_voice_by_elevenlabs_id,
        search_jarvis_voices,
        _normalize_voice_id,
    )

    el_id = settings.elevenlabs_jarvis_voice_id.strip() or JARVIS_CLONED_ELEVENLABS_ID
    configured = _normalize_voice_id(settings.retell_voice_id)
    mapped = find_retell_voice_by_elevenlabs_id(client, configured or el_id)
    retell_id, err = ensure_jarvis_voice_in_retell(client)
    agent_voice_id: str | None = None
    agent_ref = get_retell_agent_id() or settings.retell_agent_id.strip()
    if agent_ref:
        try:
            agent_voice_id = str(getattr(client.agent.retrieve(agent_id=agent_ref), "voice_id", "") or "") or None
        except Exception:  # noqa: BLE001
            pass

    return {
        "ok": bool(mapped or retell_id or (agent_voice_id and agent_voice_id != "11labs-Brian")),
        "elevenlabs_voice_id": el_id,
        "configured_retell_voice_id": configured or None,
        "retell_voice_id_from_library": mapped,
        "retell_voice_id": mapped or retell_id,
        "agent_voice_id": agent_voice_id,
        "jarvis_voice_matches": search_jarvis_voices(client, query=configured or el_id),
        "error": err,
        "hint": (
            "RETELL_VOICE_ID debe ser el ID de Retell (ej. custom-xxx), NO el de ElevenLabs. "
            "En Retell dashboard → Voices → copie el voice_id de su clon Jarvis."
        ),
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
    """Estado Retell sin auth — reintenta bootstrap si falta agente."""
    settings = get_settings()
    info = get_last_bootstrap_info() or {}
    agent_id = get_retell_agent_id()
    bootstrap_error: str | None = None

    if not agent_id and settings.voice_provider == "retell":
        try:
            result = bootstrap_retell_if_needed()
            if result:
                agent_id = result.get("agent_id") or get_retell_agent_id()
                info = result
            else:
                bootstrap_error = "bootstrap_retell_if_needed returned None — revise logs Railway"
        except Exception as exc:  # noqa: BLE001
            bootstrap_error = str(exc)
            logger.exception("[RETELL] status bootstrap retry failed")

    return {
        "ok": True,
        "voice_provider": settings.voice_provider,
        "agent_configured": bool(agent_id),
        "agent_id": agent_id or None,
        "voice_id": info.get("voice_id") or settings.retell_voice_id.strip() or "11labs-George",
        "llm_websocket_url": info.get("llm_websocket_url"),
        "brain": settings.gemini_voice_model,
        "has_retell_api_key": bool(settings.retell_api_key.strip()),
        "has_google_api_key": bool(settings.google_api_key.strip()),
        "api_public_url": settings.api_public_url,
        "bootstrap_error": get_last_bootstrap_error() or bootstrap_error,
    }


@router.post("/admin/bootstrap")
async def retell_bootstrap_agent(user_id: str = Depends(require_user_id)) -> dict[str, Any]:
    """Bootstrap manual del agente (admin/dev). Requiere usuario autenticado."""
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
