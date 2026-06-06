"""Gemini Live — endpoints protegidos."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.config import get_settings
from app.deps.auth import require_user_id

logger = logging.getLogger(__name__)
from app.domain.ced_live_voice_prompt import CED_LIVE_VOICE_SYSTEM_PROMPT
from app.domain.gemini_voices import VALID_GEMINI_VOICES
from app.services.gemini_live import create_ephemeral_token
from app.services.gemini_grounded import fetch_voice_brief
from app.services.gemini_deep_analysis import consultar_sistema_avanzado

router = APIRouter(prefix="/v1/gemini", tags=["gemini"])


class EphemeralTokenBody(BaseModel):
    voice_name: str | None = Field(default=None, alias="voiceName")

    model_config = {"populate_by_name": True}


class VoiceBriefBody(BaseModel):
    query: str = Field(default="", max_length=500)
    kind: str = Field(default="news")


class DeepAnalysisBody(BaseModel):
    prompt: str = Field(default="", max_length=2000)


@router.post("/ephemeral-token")
async def ephemeral_token(
    body: EphemeralTokenBody | None = None,
    user_id: str = Depends(require_user_id),
) -> dict:
    """Token de un solo uso para Live API (nunca expone GOOGLE_API_KEY)."""
    voice = body.voice_name if body else None
    result = create_ephemeral_token(voice_name=voice)
    if result.get("ok"):
        result["userId"] = user_id
    return result


@router.post("/voice-brief")
async def voice_brief(
    body: VoiceBriefBody,
    _user_id: str = Depends(require_user_id),
) -> dict:
    """Resumen hablable — Tavily + Gemini Search (no bloquea el event loop)."""
    kind = body.kind if body.kind in ("news", "general", "weather") else "news"
    return await asyncio.to_thread(fetch_voice_brief, body.query, kind=kind)


@router.post("/deep-analysis")
async def deep_analysis(
    body: DeepAnalysisBody,
    _user_id: str = Depends(require_user_id),
) -> dict:
    """Herramienta Live `consultar_sistema_avanzado` — solo backend."""
    return await asyncio.to_thread(consultar_sistema_avanzado, body.prompt)


@router.get("/voices")
async def list_voices(_user_id: str = Depends(require_user_id)) -> dict:
    """Lista de voces PrebuiltVoiceConfig soportadas."""
    return {"voices": sorted(VALID_GEMINI_VOICES)}


@router.get("/test")
async def test_gemini() -> dict:
    """Test simple de API key + billing (sin Live API)."""
    settings = get_settings()
    api_key = settings.google_api_key.strip()
    if not api_key:
        return {"ok": False, "error": "GOOGLE_API_KEY no configurada"}

    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents="Di exactamente: Hola desde CED",
        )
        text = getattr(response, "text", None) or ""
        logger.info("[GEMINI:TEST] ok response_len=%s", len(text))
        return {
            "ok": True,
            "model": "gemini-2.5-flash",
            "response": text.strip(),
            "billing": "active",
        }
    except Exception as e:
        logger.error("[GEMINI:TEST] %s: %s", type(e).__name__, e)
        return {
            "ok": False,
            "error": str(e),
            "type": type(e).__name__,
        }


@router.get("/config")
async def gemini_config(_user_id: str = Depends(require_user_id)) -> dict:
    """Metadatos públicos de sesión (sin secretos)."""
    from app.domain.gemini_models import RECOMMENDED_LIVE_MODEL
    from app.services.gemini_live import DEFAULT_LIVE_MODEL

    return {
        "model": DEFAULT_LIVE_MODEL,
        "recommended": RECOMMENDED_LIVE_MODEL,
        "systemInstructionPreview": CED_LIVE_VOICE_SYSTEM_PROMPT[:200] + "…",
        "audioBidirectional": True,
        "videoSupported": True,
    }
