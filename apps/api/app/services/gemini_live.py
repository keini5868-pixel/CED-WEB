"""Gemini Live — tokens efímeros (API key solo en servidor)."""



from __future__ import annotations



import datetime
import logging

from typing import Any

logger = logging.getLogger(__name__)



from app.config import get_settings

from app.domain.ced_live_voice_prompt import CED_LIVE_VOICE_SYSTEM_PROMPT

from app.domain.gemini_models import RECOMMENDED_LIVE_MODEL

from app.domain.gemini_voices import normalize_voice_name



DEFAULT_LIVE_MODEL = RECOMMENDED_LIVE_MODEL





def create_ephemeral_token(voice_name: str | None = None) -> dict[str, Any]:

    settings = get_settings()

    api_key = settings.google_api_key.strip()

    if not api_key:

        return {"ok": False, "error": "GOOGLE_API_KEY no configurada en apps/api/.env"}



    try:

        from google import genai

        from google.genai import types

    except ImportError:

        return {"ok": False, "error": "Instala google-genai en el entorno API"}



    model = getattr(settings, "gemini_live_model", None) or DEFAULT_LIVE_MODEL

    voice = normalize_voice_name(voice_name)
    logger.info("[GEMINI:1] Token efímero model=%s voice=%s", model, voice)

    now = datetime.datetime.now(tz=datetime.timezone.utc)



    client = genai.Client(

        api_key=api_key,

        http_options=types.HttpOptions(api_version="v1alpha"),

    )



    token = client.auth_tokens.create(

        config={

            "uses": 1,

            "expire_time": now + datetime.timedelta(minutes=30),

            "new_session_expire_time": now + datetime.timedelta(minutes=15),

            "http_options": {"api_version": "v1alpha"},

        },

    )



    token_value = getattr(token, "name", None) or getattr(token, "token", None)

    if not token_value and hasattr(token, "model_dump"):

        dumped = token.model_dump()

        token_value = dumped.get("name") or dumped.get("token")



    if not token_value:

        return {"ok": False, "error": "No se pudo generar token efímero"}



    logger.info("[GEMINI:4] Token generado voice=%s", voice)
    return {

        "ok": True,

        "token": str(token_value),

        "model": model,

        "voiceName": voice,

        "systemInstruction": CED_LIVE_VOICE_SYSTEM_PROMPT,

        "expiresInSeconds": 120,

    }


