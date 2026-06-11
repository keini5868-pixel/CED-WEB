"""OpenAI — voz Realtime y herramientas auxiliares."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from app.deps.auth import require_user_id
from app.domain.openai_voice_prompt import OPENAI_REALTIME_SYSTEM_PROMPT
from app.services.claude_deep_analysis import consultar_sistema_avanzado
from app.services.gemini_grounded import fetch_voice_brief
from app.services.openai_realtime import create_realtime_session, negotiate_realtime_call
from app.services.openai_voice_config import OPENAI_VOICES, normalize_openai_voice
from app.services.voice_usage import voice_access_state

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/openai", tags=["openai"])


class RealtimeSessionBody(BaseModel):
    voice_name: str | None = Field(default=None, alias="voiceName")

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
    balance = voice_access_state(user_id)
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
    result = create_realtime_session(user_id=user_id, voice_name=voice)
    if result.get("ok"):
        result["userId"] = user_id
        result["usagePercent"] = balance.get("usage_percent", 0)
        result["warningLevel"] = _warning_level(balance.get("usage_percent", 0))
    return result


@router.post("/realtime/calls")
async def realtime_calls(
    request: Request,
    x_openai_ephemeral_key: str = Header(..., alias="X-OpenAI-Ephemeral-Key"),
    _user_id: str = Depends(require_user_id),
) -> PlainTextResponse | dict:
    """Negocia WebRTC SDP con OpenAI usando token efímero (proxy anti-CORS)."""
    sdp_offer = (await request.body()).decode("utf-8", errors="replace")
    result = negotiate_realtime_call(client_secret=x_openai_ephemeral_key, sdp_offer=sdp_offer)
    if not result.get("ok"):
        return result
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
    from app.services.openai_images import generate_image
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
