"""OpenAI Realtime — sesiones efímeras (API key solo en servidor)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings
from app.domain.openai_voice_prompt import OPENAI_REALTIME_SYSTEM_PROMPT
from app.services.openai_key_utils import openai_api_key_looks_valid, sanitize_openai_api_key
from app.services.openai_voice_config import (
    REALTIME_MAX_OUTPUT_TOKENS,
    REALTIME_TEMPERATURE,
    normalize_openai_voice,
)
from app.services.openai_voice_tools import OPENAI_REALTIME_TOOLS

logger = logging.getLogger(__name__)

OPENAI_CLIENT_SECRETS_URL = "https://api.openai.com/v1/realtime/client_secrets"

DEFAULT_REALTIME_MODEL = "gpt-realtime-mini"
FALLBACK_MODELS = (
    "gpt-realtime-mini",
    "gpt-realtime",
    "gpt-4o-mini-realtime-preview-2024-12-17",
    "gpt-4o-realtime-preview-2024-12-17",
)


def _resolve_model(settings_model: str) -> str:
    model = (settings_model or DEFAULT_REALTIME_MODEL).strip()
    aliases = {
        "gpt-4o-mini-realtime-preview": "gpt-4o-mini-realtime-preview-2024-12-17",
        "gpt-4o-realtime-preview": "gpt-4o-realtime-preview-2024-12-17",
    }
    return aliases.get(model, model)


def _models_to_try(primary: str) -> list[str]:
    ordered = [primary, *FALLBACK_MODELS]
    seen: set[str] = set()
    out: list[str] = []
    for m in ordered:
        if m and m not in seen:
            seen.add(m)
            out.append(m)
    return out


def _build_minimal_ga_payload(
    *,
    model: str,
    voice: str,
    instructions: str,
) -> dict[str, Any]:
    return {
        "expires_after": {"seconds": 600},
        "session": {
            "type": "realtime",
            "model": model,
            "instructions": instructions[:8000],
            "audio": {
                "output": {"voice": voice},
            },
        },
    }


def _build_full_ga_payload(
    *,
    model: str,
    voice: str,
    instructions: str,
    with_tools: bool,
) -> dict[str, Any]:
    session: dict[str, Any] = {
        "type": "realtime",
        "model": model,
        "instructions": instructions[:8000],
        "output_modalities": ["audio"],
        "audio": {
            "input": {
                "format": {"type": "audio/pcm", "rate": 24000},
                "transcription": {"model": "whisper-1"},
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.45,
                    "prefix_padding_ms": 200,
                    "silence_duration_ms": 400,
                    "create_response": True,
                    "interrupt_response": True,
                },
            },
            "output": {
                "format": {"type": "audio/pcm", "rate": 24000},
                "voice": voice,
            },
        },
        "max_output_tokens": REALTIME_MAX_OUTPUT_TOKENS,
        "temperature": REALTIME_TEMPERATURE,
    }
    if with_tools:
        session["tools"] = OPENAI_REALTIME_TOOLS
        session["tool_choice"] = "auto"
    return {"expires_after": {"seconds": 600}, "session": session}


def _parse_openai_error(res: httpx.Response) -> str:
    try:
        body = res.json()
        err = body.get("error") or {}
        msg = err.get("message") or body.get("message")
        code = err.get("code")
        if msg:
            if code == "invalid_api_key":
                return "API key inválida. Crea una nueva en platform.openai.com/api-keys."
            return str(msg)[:220]
    except Exception:  # noqa: BLE001
        pass
    return f"HTTP {res.status_code}"


def _extract_client_secret(data: dict[str, Any]) -> str | None:
    if data.get("value"):
        return str(data["value"])
    cs = data.get("client_secret")
    if isinstance(cs, dict) and cs.get("value"):
        return str(cs["value"])
    if isinstance(cs, str) and cs:
        return cs
    return None


def _post_session(
    client: httpx.Client,
    *,
    api_key: str,
    payload: dict[str, Any],
    project_id: str = "",
) -> httpx.Response:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if project_id.strip():
        headers["OpenAI-Project"] = project_id.strip()
    return client.post(OPENAI_CLIENT_SECRETS_URL, headers=headers, json=payload)


def create_realtime_session(
    *,
    user_id: str,
    voice_name: str | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    api_key = sanitize_openai_api_key(settings.openai_api_key)
    if not api_key:
        return {"ok": False, "error": "OPENAI_API_KEY no configurada en Railway (CED-WEB)."}
    if not openai_api_key_looks_valid(api_key):
        return {
            "ok": False,
            "error": (
                "OPENAI_API_KEY tiene formato inválido. Debe empezar con sk-proj- "
                "y pegarse sin comillas en Railway (CED-WEB)."
            ),
            "code": "invalid_api_key_format",
        }

    voice = normalize_openai_voice(voice_name)
    model = _resolve_model(settings.openai_model_voice)
    project_id = getattr(settings, "openai_project_id", "") or ""

    instructions = OPENAI_REALTIME_SYSTEM_PROMPT
    try:
        from app.services.cognitive_router import build_voice_system_extras

        extras = build_voice_system_extras(user_id)
        if extras:
            instructions = f"{instructions}\n\n{extras}"
    except Exception:  # noqa: BLE001
        pass

    attempts: list[tuple[str, dict[str, Any]]] = []
    for m in _models_to_try(model):
        attempts.append((f"minimal:{m}", _build_minimal_ga_payload(model=m, voice=voice, instructions=instructions)))
        attempts.append((f"full:{m}", _build_full_ga_payload(model=m, voice=voice, instructions=instructions, with_tools=False)))
        attempts.append((f"tools:{m}", _build_full_ga_payload(model=m, voice=voice, instructions=instructions, with_tools=True)))

    last_error = "OpenAI rechazó la sesión Realtime."
    try:
        with httpx.Client(timeout=30.0) as client:
            for label, payload in attempts:
                res = _post_session(client, api_key=api_key, payload=payload, project_id=project_id)
                if res.status_code < 400:
                    data = res.json()
                    client_secret = _extract_client_secret(data)
                    if not client_secret:
                        last_error = "OpenAI no devolvió client_secret."
                        continue
                    used_model = payload.get("session", {}).get("model") or model
                    logger.info(
                        "[OPENAI] session ok via=%s model=%s voice=%s user=%s",
                        label,
                        used_model,
                        voice,
                        user_id[:8],
                    )
                    return {
                        "ok": True,
                        "clientSecret": client_secret,
                        "model": used_model,
                        "voiceName": voice,
                        "systemInstruction": instructions,
                        "expiresInSeconds": 600,
                        "sampleRate": 24000,
                    }

                detail = res.text[:400]
                parsed = _parse_openai_error(res)
                logger.error("[OPENAI] session create %s %s: %s", label, res.status_code, detail)
                last_error = f"OpenAI Realtime ({res.status_code}): {parsed}"
    except Exception as exc:  # noqa: BLE001
        logger.exception("[OPENAI] session create failed")
        return {"ok": False, "error": f"No se pudo contactar OpenAI: {exc}"}

    return {"ok": False, "error": last_error}
