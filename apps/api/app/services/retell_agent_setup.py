"""Bootstrap agente Retell CED — LLM + agent + tools."""

from __future__ import annotations

import logging
from typing import Any

from app.config import get_settings
from app.domain.openai_voice_prompt import CED_MINIMAL_REALTIME_PROMPT
from app.services.retell_client import get_retell_client
from app.services.retell_tools import build_retell_general_tools

logger = logging.getLogger(__name__)

DEFAULT_VOICE_ID = "11labs-George"


def resolve_retell_voice_id() -> str:
    settings = get_settings()
    configured = settings.retell_voice_id.strip()
    if configured:
        return configured
    return DEFAULT_VOICE_ID


def ensure_retell_llm(*, llm_id: str | None = None) -> str:
    """Crea o actualiza Retell LLM con prompt y tools CED."""
    client = get_retell_client()
    if not client:
        raise RuntimeError("RETELL_API_KEY no configurada")

    tools = build_retell_general_tools()
    payload: dict[str, Any] = {
        "general_prompt": CED_MINIMAL_REALTIME_PROMPT,
        "general_tools": tools,
        "begin_message": "A su servicio, señor.",
    }

    if llm_id:
        client.llm.update(llm_id=llm_id, **payload)
        logger.info("[RETELL] LLM actualizado: %s (%s tools)", llm_id, len(tools))
        return llm_id

    created = client.llm.create(**payload)
    new_id = str(created.llm_id)
    logger.info("[RETELL] LLM creado: %s (%s tools)", new_id, len(tools))
    return new_id


def ensure_retell_agent(*, agent_id: str | None = None, llm_id: str | None = None) -> dict[str, str]:
    """Crea o actualiza agente de voz Jarvis."""
    client = get_retell_client()
    if not client:
        raise RuntimeError("RETELL_API_KEY no configurada")

    settings = get_settings()
    voice_id = resolve_retell_voice_id()
    webhook = f"{settings.api_public_url.rstrip('/')}/v1/retell/webhook"

    resolved_llm = llm_id or settings.retell_llm_id.strip()
    if not resolved_llm:
        resolved_llm = ensure_retell_llm()
    else:
        ensure_retell_llm(llm_id=resolved_llm)

    agent_payload: dict[str, Any] = {
        "response_engine": {"type": "retell-llm", "llm_id": resolved_llm},
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
        logger.info("[RETELL] Agente actualizado: %s voice=%s", agent_id, voice_id)
        return {"agent_id": agent_id, "llm_id": resolved_llm, "voice_id": voice_id}

    created = client.agent.create(**agent_payload)
    new_agent = str(created.agent_id)
    logger.info("[RETELL] Agente creado: %s voice=%s", new_agent, voice_id)
    return {"agent_id": new_agent, "llm_id": resolved_llm, "voice_id": voice_id}


def bootstrap_retell_on_startup() -> None:
    """Opcional al arrancar API si RETELL_AUTO_BOOTSTRAP=true."""
    settings = get_settings()
    if settings.voice_provider != "retell":
        return
    if not settings.retell_auto_bootstrap:
        return
    if not settings.retell_api_key.strip():
        logger.warning("[RETELL] auto-bootstrap omitido — sin RETELL_API_KEY")
        return
    try:
        agent_id = settings.retell_agent_id.strip() or None
        llm_id = settings.retell_llm_id.strip() or None
        result = ensure_retell_agent(agent_id=agent_id, llm_id=llm_id)
        logger.info(
            "[RETELL] bootstrap ok agent=%s llm=%s",
            result["agent_id"],
            result["llm_id"],
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("[RETELL] bootstrap failed: %s", exc)
