"""OpenAI Realtime — sesiones efímeras (API key solo en servidor)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings
from app.domain.openai_voice_prompt import OPENAI_REALTIME_SYSTEM_PROMPT
from app.services.openai_voice_config import (
    REALTIME_MAX_OUTPUT_TOKENS,
    REALTIME_TEMPERATURE,
    normalize_openai_voice,
)
from app.services.openai_voice_tools import OPENAI_REALTIME_TOOLS

logger = logging.getLogger(__name__)

OPENAI_REALTIME_SESSIONS_URL = "https://api.openai.com/v1/realtime/sessions"


def create_realtime_session(
    *,
    user_id: str,
    voice_name: str | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    api_key = settings.openai_api_key.strip()
    if not api_key:
        return {"ok": False, "error": "OPENAI_API_KEY no configurada en Railway (CED-WEB)."}

    voice = normalize_openai_voice(voice_name)
    model = settings.openai_model_voice.strip() or "gpt-4o-mini-realtime-preview"

    instructions = OPENAI_REALTIME_SYSTEM_PROMPT
    try:
        from app.services.cognitive_router import build_voice_system_extras

        extras = build_voice_system_extras(user_id)
        if extras:
            instructions = f"{instructions}\n\n{extras}"
    except Exception:  # noqa: BLE001
        pass

    payload: dict[str, Any] = {
        "model": model,
        "voice": voice,
        "instructions": instructions[:8000],
        "tools": OPENAI_REALTIME_TOOLS,
        "input_audio_format": "pcm16",
        "output_audio_format": "pcm16",
        "input_audio_transcription": {"model": "whisper-1"},
        "turn_detection": {
            "type": "server_vad",
            "threshold": 0.5,
            "prefix_padding_ms": 300,
            "silence_duration_ms": 400,
            "create_response": True,
        },
        "temperature": REALTIME_TEMPERATURE,
        "max_response_output_tokens": REALTIME_MAX_OUTPUT_TOKENS,
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            res = client.post(
                OPENAI_REALTIME_SESSIONS_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            if res.status_code >= 400:
                detail = res.text[:400]
                logger.error("[OPENAI] session create %s: %s", res.status_code, detail)
                return {
                    "ok": False,
                    "error": f"OpenAI rechazó la sesión ({res.status_code}). Revisa OPENAI_API_KEY y saldo.",
                }
            data = res.json()
    except Exception as exc:  # noqa: BLE001
        logger.exception("[OPENAI] session create failed")
        return {"ok": False, "error": f"No se pudo contactar OpenAI: {exc}"}

    client_secret = (data.get("client_secret") or {}).get("value")
    if not client_secret:
        return {"ok": False, "error": "OpenAI no devolvió client_secret."}

    logger.info("[OPENAI] session ok model=%s voice=%s user=%s", model, voice, user_id[:8])
    return {
        "ok": True,
        "clientSecret": client_secret,
        "model": model,
        "voiceName": voice,
        "systemInstruction": instructions,
        "expiresInSeconds": 600,
        "sampleRate": 24000,
    }
