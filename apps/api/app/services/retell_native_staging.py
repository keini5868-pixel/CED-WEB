"""Agente Retell LLM nativo de staging — aislado del Custom LLM de producción."""

from __future__ import annotations

import logging
from typing import Any

from app.config import get_settings
from app.services.retell_agent_cache import (
    get_retell_agent_id,
    set_native_staging_agent,
)
from app.services.retell_agent_setup import (
    _retrieve_agent_voice_id,
    _voice_model_for,
    _voice_speed_for,
    _voice_temperature_for,
    _voice_volume_for,
    resolve_retell_voice_id,
)
from app.services.retell_client import get_retell_client
from app.services.retell_native_pilot import (
    NATIVE_PILOT_GREETING,
    RETELL_NATIVE_PILOT_PROMPT,
    STAGING_AGENT_NAME,
    build_native_pilot_llm_config,
)

logger = logging.getLogger(__name__)


def _resolve_staging_voice_id(client: Any) -> str:
    """Misma voz Jarvis que producción — nunca modifica el agente prod."""
    prod_agent_id = get_retell_agent_id()
    if prod_agent_id:
        dashboard_voice = _retrieve_agent_voice_id(client, prod_agent_id)
        if dashboard_voice:
            logger.info("[NATIVE-PILOT] voz copiada del agente prod: %s", dashboard_voice)
            return dashboard_voice
    return resolve_retell_voice_id(client)


def _llm_payload(*, api_public_url: str, with_tools: bool) -> dict[str, Any]:
    settings = get_settings()
    model = (settings.retell_native_pilot_model or "gemini-3.0-flash").strip()
    payload: dict[str, Any] = {
        "model": model,
        "model_temperature": 0,
        "start_speaker": "agent",
        "begin_message": NATIVE_PILOT_GREETING,
        "general_prompt": RETELL_NATIVE_PILOT_PROMPT,
    }
    if with_tools:
        llm_tools = build_native_pilot_llm_config(api_public_url=api_public_url)
        payload.update(llm_tools)
    return payload


def ensure_native_staging_llm(*, llm_id: str | None = None, with_tools: bool = True) -> dict[str, str]:
    """Crea o actualiza el Retell LLM de staging (response engine nativo)."""
    client = get_retell_client()
    if not client:
        raise RuntimeError("RETELL_API_KEY no configurada")

    settings = get_settings()
    api_public_url = settings.api_public_url.rstrip("/")
    payload = _llm_payload(api_public_url=api_public_url, with_tools=with_tools)

    if llm_id:
        try:
            client.llm.update(llm_id=llm_id, **payload)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[NATIVE-PILOT] llm.update failed (%s) — recreando", exc)
            llm_id = None

    if not llm_id:
        created = client.llm.create(**payload)
        llm_id = str(getattr(created, "llm_id", "") or "").strip()
        if not llm_id:
            raise RuntimeError("Retell llm.create no devolvió llm_id")

    logger.info("[NATIVE-PILOT] LLM staging listo id=%s model=%s tools=%s", llm_id, payload["model"], with_tools)
    return {
        "llm_id": llm_id,
        "model": payload["model"],
        "with_tools": str(with_tools).lower(),
    }


def ensure_native_staging_agent(
    *,
    agent_id: str | None = None,
    llm_id: str | None = None,
    with_tools: bool = True,
) -> dict[str, str]:
    """Crea o actualiza agente Retell nativo de staging — NO toca producción."""
    client = get_retell_client()
    if not client:
        raise RuntimeError("RETELL_API_KEY no configurada")

    settings = get_settings()
    voice_id = _resolve_staging_voice_id(client)
    webhook = f"{settings.api_public_url.rstrip('/')}/v1/retell/webhook"

    if not llm_id:
        llm_id = settings.retell_native_staging_llm_id.strip() or None
    llm_info = ensure_native_staging_llm(llm_id=llm_id, with_tools=with_tools)
    llm_id = llm_info["llm_id"]

    agent_payload: dict[str, Any] = {
        "response_engine": {
            "type": "retell-llm",
            "llm_id": llm_id,
        },
        "voice_id": voice_id,
        "voice_speed": _voice_speed_for(voice_id),
        "voice_temperature": _voice_temperature_for(voice_id),
        "volume": _voice_volume_for(voice_id),
        "responsiveness": 0.85,
        "interruption_sensitivity": settings.retell_interruption_sensitivity,
        "denoising_mode": settings.retell_denoising_mode,
        "language": "es-419",
        "stt_mode": "accurate",
        "webhook_url": webhook,
        "webhook_events": ["call_started", "call_ended", "call_analyzed"],
        "begin_message_delay_ms": 0,
        "agent_name": STAGING_AGENT_NAME,
    }
    voice_model = _voice_model_for(voice_id)
    if voice_model:
        agent_payload["voice_model"] = voice_model

    if agent_id:
        try:
            client.agent.update(agent_id=agent_id, **agent_payload)
        except Exception as exc:
            err = str(exc).lower()
            if "voice model" in err or "voice_model" in err:
                agent_payload.pop("voice_model", None)
                client.agent.update(agent_id=agent_id, **agent_payload)
            else:
                raise
        logger.info("[NATIVE-PILOT] Agente staging actualizado: %s voice=%s llm=%s", agent_id, voice_id, llm_id)
        out = {
            "agent_id": agent_id,
            "llm_id": llm_id,
            "voice_id": voice_id,
            "engine": "retell-llm",
            "model": llm_info["model"],
            "agent_name": STAGING_AGENT_NAME,
        }
        set_native_staging_agent(agent_id, out)
        return out

    created = client.agent.create(**agent_payload)
    new_agent = str(getattr(created, "agent_id", "") or "").strip()
    if not new_agent:
        raise RuntimeError("Retell agent.create no devolvió agent_id")

    logger.info("[NATIVE-PILOT] Agente staging creado: %s voice=%s llm=%s", new_agent, voice_id, llm_id)
    out = {
        "agent_id": new_agent,
        "llm_id": llm_id,
        "voice_id": voice_id,
        "engine": "retell-llm",
        "model": llm_info["model"],
        "agent_name": STAGING_AGENT_NAME,
    }
    set_native_staging_agent(new_agent, out)
    return out


def bootstrap_native_staging_pilot(*, with_tools: bool = True) -> dict[str, str]:
    """Bootstrap completo del piloto nativo — producción intacta."""
    settings = get_settings()
    agent_id = settings.retell_native_staging_agent_id.strip() or None
    llm_id = settings.retell_native_staging_llm_id.strip() or None
    result = ensure_native_staging_agent(agent_id=agent_id, llm_id=llm_id, with_tools=with_tools)

    logger.critical(
        "═══════════════════════════════════════════════════\n"
        "RETELL NATIVE PILOT OK — agregue en Railway (staging):\n"
        "RETELL_NATIVE_STAGING_AGENT_ID=%s\n"
        "RETELL_NATIVE_STAGING_LLM_ID=%s\n"
        "═══════════════════════════════════════════════════",
        result["agent_id"],
        result["llm_id"],
    )
    return result
