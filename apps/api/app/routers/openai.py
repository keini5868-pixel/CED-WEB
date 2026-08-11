"""OpenAI — voz Realtime y herramientas auxiliares."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from app.config import get_settings
from app.deps.auth import require_user_id
from app.domain.openai_voice_prompt import OPENAI_REALTIME_SYSTEM_PROMPT
from app.services.claude_deep_analysis import consultar_sistema_avanzado
from app.services.gemini_grounded import fetch_voice_brief
from app.services.openai_realtime import create_realtime_session, negotiate_realtime_call
from app.services.openai_voice_config import OPENAI_VOICES, normalize_openai_voice
from app.services.voice_usage import voice_access_state_async

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/openai", tags=["openai"])


def _allow_openai_realtime(
    user_id: str,
    balance: dict,
    *,
    voice_profile: str | None = None,
) -> bool:
    """Abre Realtime para Cierre/FitLine aunque VOICE_PROVIDER=retell.

    Casos:
    - Plan Cierre (o transporte/stack ya marcado openai/gemini)
    - Preview admin «socio Cierre»
    - Admin pidiendo voice_profile=fitline (UI PM / preview a veces sin ContextVar)
    """
    settings = get_settings()
    if settings.voice_provider == "openai":
        return True

    from app.domain.plans import plan_uses_gemini_voice_stack
    from app.services.preview_persona import (
        is_cierre_partner_preview,
        user_may_use_preview,
    )

    plan_id = str(balance.get("plan_id") or "")
    if plan_uses_gemini_voice_stack(plan_id):
        return True
    if str(balance.get("voice_transport") or "").strip().lower() == "openai":
        return True
    if str(balance.get("voice_stack") or "").strip().lower() == "gemini":
        return True
    if is_cierre_partner_preview(user_id):
        return True

    profile = (voice_profile or "").strip().lower()
    if profile == "fitline" and user_may_use_preview(user_id):
        logger.info(
            "[REALTIME] allow fitline profile for admin user=%s",
            (user_id or "")[:8],
        )
        return True
    return False


class RealtimeSessionBody(BaseModel):
    voice_name: str | None = Field(default=None, alias="voiceName")
    language: str | None = Field(default="es")
    response_speed: str | None = Field(default="balanced", alias="responseSpeed")
    voice_pace: int | None = Field(default=38, alias="voicePace")
    voice_warmth: int | None = Field(default=42, alias="voiceWarmth")
    voice_energy: int | None = Field(default=38, alias="voiceEnergy")
    voice_profile: str | None = Field(default="jarvis", alias="voiceProfile")

    model_config = {"populate_by_name": True}


class VoiceBriefBody(BaseModel):
    query: str = Field(default="", max_length=500)
    kind: str = Field(default="news")


class DeepAnalysisBody(BaseModel):
    prompt: str = Field(default="", max_length=2000)


class ImageGenerateBody(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    quality: str = Field(default="auto")


@router.post("/realtime/session")
async def realtime_session(
    body: RealtimeSessionBody | None = None,
    user_id: str = Depends(require_user_id),
) -> dict:
    """Sesión efímera OpenAI Realtime — verifica límites duros antes de conectar."""
    balance = await voice_access_state_async(user_id)
    requested_profile = (
        (body.voice_profile if body and body.voice_profile else "") or ""
    ).strip().lower()
    # FitLine/Cierre siempre puede usar este transporte (sin Jarvis).
    # El resto solo si VOICE_PROVIDER=openai.
    if not _allow_openai_realtime(user_id, balance, voice_profile=requested_profile):
        return {
            "ok": False,
            "error": "OpenAI Realtime deshabilitado. Voz activa vía Retell.",
            "code": "legacy_disabled",
        }
    if balance.get("access_denied"):
        return {"ok": False, "error": "Acceso de voz no disponible. Elige un plan en Precios."}
    if balance.get("blocked"):
        return {
            "ok": False,
            "error": "Alcanzaste tu límite diario de voz. Recarga o vuelve mañana.",
            "blocked": True,
        }
    if balance.get("plan_minutes_daily", 0) <= 0 and balance.get("access_message") == "free_basic":
        return {
            "ok": False,
            "error": "La voz no está incluida en el plan Básico gratis.",
            "blocked": True,
        }

    voice = body.voice_name if body else None
    lang = (body.language if body else None) or "es"
    if lang not in ("es", "en", "pt"):
        lang = "es"
    speed = (body.response_speed if body else None) or "balanced"
    if speed not in ("fast", "balanced", "thoughtful"):
        speed = "balanced"
    pace = max(0, min(100, int(body.voice_pace if body and body.voice_pace is not None else 38)))
    warmth = max(0, min(100, int(body.voice_warmth if body and body.voice_warmth is not None else 42)))
    energy = max(0, min(100, int(body.voice_energy if body and body.voice_energy is not None else 38)))
    fitline_mode = (
        requested_profile == "fitline"
        or plan_uses_gemini_voice_stack_safe(balance)
        or str(balance.get("voice_stack") or "").lower() == "gemini"
    )
    try:
        from app.services.preview_persona import is_cierre_partner_preview

        if is_cierre_partner_preview(user_id):
            fitline_mode = True
    except Exception:  # noqa: BLE001
        pass
    if fitline_mode:
        # Sin branding Jarvis — voz masculina profesional para FitLine/Cierre.
        profile = "fitline"
        voice = voice or "cedar"
    else:
        profile = requested_profile or "jarvis"
        if profile not in ("standard", "jarvis", "fitline"):
            profile = "jarvis"
    result = await asyncio.to_thread(
        create_realtime_session,
        user_id=user_id,
        voice_name=voice,
        language=lang,
        response_speed=speed,
        voice_pace=pace,
        voice_warmth=warmth,
        voice_energy=energy,
        voice_profile=profile,
    )
    if result.get("ok"):
        result["userId"] = user_id
        result["usagePercent"] = balance.get("usage_percent", 0)
        result["warningLevel"] = _warning_level(balance.get("usage_percent", 0))
        result["voiceStack"] = balance.get("voice_stack")
        result["voiceTransport"] = balance.get("voice_transport")
    return result


def plan_uses_gemini_voice_stack_safe(balance: dict) -> bool:
    from app.domain.plans import plan_uses_gemini_voice_stack

    return plan_uses_gemini_voice_stack(str(balance.get("plan_id") or ""))


@router.post("/realtime/calls", response_model=None)
async def realtime_calls(
    request: Request,
    x_openai_ephemeral_key: str = Header(..., alias="X-OpenAI-Ephemeral-Key"),
    user_id: str = Depends(require_user_id),
):
    """Negocia WebRTC SDP con OpenAI usando token efímero (proxy anti-CORS)."""
    balance = await voice_access_state_async(user_id)
    if not _allow_openai_realtime(user_id, balance, voice_profile="fitline"):
        return JSONResponse(
            status_code=503,
            content={
                "ok": False,
                "error": "OpenAI Realtime deshabilitado.",
                "code": "legacy_disabled",
            },
        )
    sdp_offer = (await request.body()).decode("utf-8", errors="replace")
    result = negotiate_realtime_call(client_secret=x_openai_ephemeral_key, sdp_offer=sdp_offer)
    if not result.get("ok"):
        return JSONResponse(status_code=400, content=result)
    return PlainTextResponse(content=str(result["sdpAnswer"]), media_type="application/sdp")

def _warning_level(pct: float) -> str | None:
    if pct >= 100:
        return "blocked"
    if pct >= 95:
        return "critical"
    if pct >= 80:
        return "warn"
    return None


@router.post("/voice-brief")
async def voice_brief(
    body: VoiceBriefBody,
    _user_id: str = Depends(require_user_id),
) -> dict:
    kind = body.kind if body.kind in ("news", "general", "weather") else "news"
    return await asyncio.to_thread(fetch_voice_brief, body.query, kind=kind)


@router.post("/deep-analysis")
async def deep_analysis(
    body: DeepAnalysisBody,
    _user_id: str = Depends(require_user_id),
) -> dict:
    return await asyncio.to_thread(consultar_sistema_avanzado, body.prompt)


@router.get("/voices")
async def list_voices(_user_id: str = Depends(require_user_id)) -> dict:
    return {"voices": sorted(OPENAI_VOICES), "default": normalize_openai_voice(None)}


@router.post("/images/generate")
async def generate_image_endpoint(
    body: ImageGenerateBody,
    user_id: str = Depends(require_user_id),
) -> dict:
    from app.services.gemini_images import generate_image
    from app.services import supabase_db

    plan_id = None
    try:
        sub = supabase_db.get_subscription(user_id)
        plan_id = sub.get("plan_id") if sub else None
    except Exception:  # noqa: BLE001
        pass
    return await asyncio.to_thread(
        generate_image,
        user_id=user_id,
        plan_id=plan_id,
        prompt=body.prompt,
        quality=body.quality,
    )


@router.get("/config")
async def openai_config(_user_id: str = Depends(require_user_id)) -> dict:
    from app.config import get_settings

    s = get_settings()
    return {
        "provider": "openai",
        "model": s.openai_model_voice,
        "systemInstructionPreview": OPENAI_REALTIME_SYSTEM_PROMPT[:200] + "…",
        "audioBidirectional": True,
        "sampleRate": 24000,
    }
