"""Bootstrap agente Retell CED — Custom LLM (Gemini) + ElevenLabs voice."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings
from app.services.retell_client import get_retell_client

logger = logging.getLogger(__name__)

DEFAULT_VOICE_ID = "11labs-George"

JARVIS_VOICE_HINTS = ("british", "butler", "george", "brian", "daniel", "jarvis", "formal", "deep")

# Voces ElevenLabs integradas en Retell (prefijo 11labs-)
RETELL_ELEVENLABS_NAME_MAP = {
    "george": "11labs-George",
    "brian": "11labs-Brian",
    "daniel": "11labs-Daniel",
    "callum": "11labs-Callum",
    "charlie": "11labs-Charlie",
}


def resolve_retell_voice_id() -> str:
    settings = get_settings()
    configured = settings.retell_voice_id.strip()
    if configured:
        return configured

    eleven_key = settings.elevenlabs_api_key.strip()
    if eleven_key:
        picked = _pick_elevenlabs_voice_for_retell(eleven_key)
        if picked:
            return picked

    return DEFAULT_VOICE_ID


def _pick_elevenlabs_voice_for_retell(api_key: str) -> str | None:
    """Sugiere voz Retell compatible (11labs-*) según biblioteca ElevenLabs."""
    try:
        with httpx.Client(timeout=15.0) as client:
            res = client.get(
                "https://api.elevenlabs.io/v1/voices",
                headers={"xi-api-key": api_key},
            )
            if res.status_code >= 400:
                return None
            voices = res.json().get("voices") or []
    except Exception as exc:  # noqa: BLE001
        logger.warning("[RETELL] ElevenLabs voices lookup failed: %s", exc)
        return None

    best_id: str | None = None
    best_name = ""
    best_score = -1
    for voice in voices:
        name = str(voice.get("name") or "").lower()
        labels = voice.get("labels") or {}
        label_text = " ".join(str(v) for v in labels.values()).lower()
        haystack = f"{name} {label_text}"
        score = sum(1 for hint in JARVIS_VOICE_HINTS if hint in haystack)
        if "male" in haystack or labels.get("gender") == "male":
            score += 1
        if score > best_score:
            best_score = score
            best_id = str(voice.get("voice_id") or "")
            best_name = name

    if not best_id:
        return None

    for key, retell_voice in RETELL_ELEVENLABS_NAME_MAP.items():
        if key in best_name:
            return retell_voice

    logger.info("[RETELL] ElevenLabs voice sugerida: %s (score=%s)", best_id, best_score)
    return best_id


def custom_llm_websocket_url() -> str:
    settings = get_settings()
    base = settings.api_public_url.rstrip("/")
    if base.startswith("https://"):
        ws_base = "wss://" + base[len("https://") :]
    elif base.startswith("http://"):
        ws_base = "ws://" + base[len("http://") :]
    else:
        ws_base = base
    return f"{ws_base}/llm-websocket/{{call_id}}"


def ensure_retell_agent(*, agent_id: str | None = None) -> dict[str, str]:
    """Crea o actualiza agente Retell con Custom LLM (Gemini) + ElevenLabs."""
    client = get_retell_client()
    if not client:
        raise RuntimeError("RETELL_API_KEY no configurada")

    settings = get_settings()
    if not settings.google_api_key.strip():
        raise RuntimeError("GOOGLE_API_KEY no configurada — requerida para Gemini voz")

    voice_id = settings.retell_voice_id.strip() or DEFAULT_VOICE_ID
    webhook = f"{settings.api_public_url.rstrip('/')}/v1/retell/webhook"
    llm_ws = custom_llm_websocket_url()

    agent_payload: dict[str, Any] = {
        "response_engine": {
            "type": "custom-llm",
            "llm_websocket_url": llm_ws,
        },
        "voice_id": voice_id,
        "voice_model": "eleven_turbo_v2_5",
        "voice_speed": 1.0,
        "voice_temperature": 0.8,
        "responsiveness": 1.0,
        "interruption_sensitivity": 1.0,
        "enable_backchannel": True,
        "language": "multi",
        "webhook_url": webhook,
        "agent_name": "CED Jarvis",
    }

    if agent_id:
        client.agent.update(agent_id=agent_id, **agent_payload)
        logger.info("[RETELL] Agente actualizado: %s voice=%s ws=%s", agent_id, voice_id, llm_ws)
        return {
            "agent_id": agent_id,
            "voice_id": voice_id,
            "llm_websocket_url": llm_ws,
            "brain": settings.gemini_voice_model,
        }

    created = client.agent.create(**agent_payload)
    new_agent = str(created.agent_id)
    logger.info("[RETELL] Agente creado: %s voice=%s ws=%s", new_agent, voice_id, llm_ws)
    return {
        "agent_id": new_agent,
        "voice_id": voice_id,
        "llm_websocket_url": llm_ws,
        "brain": settings.gemini_voice_model,
    }


def bootstrap_retell_if_needed() -> dict[str, str] | None:
    """Crea o actualiza agente Retell al arrancar si hay API keys."""
    settings = get_settings()
    if settings.voice_provider != "retell":
        return None
    if not settings.retell_api_key.strip():
        logger.warning("[RETELL] bootstrap omitido — sin RETELL_API_KEY")
        return None
    if not settings.google_api_key.strip():
        logger.warning("[RETELL] bootstrap omitido — sin GOOGLE_API_KEY")
        return None

    from app.services.retell_agent_cache import set_bootstrapped_agent

    agent_id = settings.retell_agent_id.strip() or None
    try:
        result = ensure_retell_agent(agent_id=agent_id)
        set_bootstrapped_agent(result["agent_id"], result)
        if not agent_id:
            logger.critical(
                "═══════════════════════════════════════════════════\n"
                "RETELL BOOTSTRAP OK — agregue en Railway:\n"
                "RETELL_AGENT_ID=%s\n"
                "RETELL_VOICE_ID=%s\n"
                "═══════════════════════════════════════════════════",
                result["agent_id"],
                result["voice_id"],
            )
        else:
            logger.info(
                "[RETELL] agente listo id=%s voice=%s",
                result["agent_id"],
                result["voice_id"],
            )
        return result
    except Exception as exc:  # noqa: BLE001
        logger.error("[RETELL] bootstrap failed: %s", exc)
        return None


def bootstrap_retell_on_startup() -> None:
    """Actualiza agente existente si RETELL_AUTO_BOOTSTRAP=true."""
    settings = get_settings()
    if not settings.retell_auto_bootstrap:
        return
    bootstrap_retell_if_needed()
