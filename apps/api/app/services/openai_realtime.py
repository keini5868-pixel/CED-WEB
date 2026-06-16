"""OpenAI Realtime — sesiones efímeras WebRTC (API key solo en servidor)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings
from app.domain.openai_voice_prompt import build_realtime_instructions
from app.services.openai_key_utils import openai_api_key_looks_valid, sanitize_openai_api_key
from app.services.openai_voice_config import (
    REALTIME_MAX_OUTPUT_TOKENS,
    REALTIME_NOISE_REDUCTION,
    REALTIME_TEMPERATURE,
    REALTIME_TURN_DETECTION,
    REALTIME_TURN_DETECTION_FALLBACK,
    normalize_openai_voice,
    profile_for_response_speed,
)
from app.services.openai_voice_tools import OPENAI_REALTIME_TOOLS

logger = logging.getLogger(__name__)

OPENAI_CLIENT_SECRETS_URL = "https://api.openai.com/v1/realtime/client_secrets"
OPENAI_REALTIME_CALLS_URL = "https://api.openai.com/v1/realtime/calls"

DEFAULT_REALTIME_MODEL = "gpt-realtime"
FALLBACK_MODELS = (
    "gpt-realtime",
    "gpt-realtime-mini",
    "gpt-4o-mini-realtime-preview-2024-12-17",
    "gpt-4o-realtime-preview-2024-12-17",
)

EXPIRES_AFTER = {"anchor": "created_at", "seconds": 600}


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


def _audio_input(turn_detection: dict[str, Any], *, language: str = "es") -> dict[str, Any]:
    transcription: dict[str, str] = {"model": "whisper-1"}
    if language in ("es", "en", "pt"):
        transcription["language"] = language
    return {
        "transcription": transcription,
        "noise_reduction": REALTIME_NOISE_REDUCTION,
        "turn_detection": turn_detection,
    }


def _build_session_payload(
    *,
    model: str,
    voice: str,
    instructions: str,
    with_tools: bool,
    turn_detection: dict[str, Any],
    language: str = "es",
    temperature: float | None = None,
) -> dict[str, Any]:
    session: dict[str, Any] = {
        "type": "realtime",
        "model": model,
        "instructions": instructions[:12000],
        "output_modalities": ["audio"],
        "audio": {
            "input": _audio_input(turn_detection, language=language),
            "output": {
                "voice": voice,
            },
        },
        "max_output_tokens": REALTIME_MAX_OUTPUT_TOKENS,
        "temperature": temperature if temperature is not None else REALTIME_TEMPERATURE,
    }
    if with_tools:
        session["tools"] = OPENAI_REALTIME_TOOLS
        session["tool_choice"] = "auto"
    return {"expires_after": EXPIRES_AFTER, "session": session}


def _build_minimal_payload(
    *,
    model: str,
    voice: str,
    instructions: str,
    turn_detection: dict[str, Any],
    language: str = "es",
) -> dict[str, Any]:
    return {
        "expires_after": EXPIRES_AFTER,
        "session": {
            "type": "realtime",
            "model": model,
            "instructions": instructions[:12000],
            "audio": {
                "input": _audio_input(turn_detection, language=language),
                "output": {"voice": voice},
            },
        },
    }


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
    language: str = "es",
    response_speed: str = "balanced",
    voice_pace: int = 38,
    voice_warmth: int = 42,
    voice_energy: int = 38,
    voice_profile: str = "jarvis",
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

    instructions = build_realtime_instructions(
        language=language or "es",
        voice_pace=voice_pace,
        voice_warmth=voice_warmth,
        voice_energy=voice_energy,
        response_speed=response_speed or "balanced",
        voice_profile=voice_profile or "jarvis",
    )
    lang = language or "es"
    temperature, preferred_turn = profile_for_response_speed(response_speed)
    address: dict[str, Any] = {}
    try:
        from app.services.cognitive_router import build_voice_system_extras
        from app.services.user_address import resolve_user_address

        extras = build_voice_system_extras(user_id)
        if extras:
            instructions = f"{instructions}\n\n{extras}"
        address = resolve_user_address(user_id)
    except Exception:  # noqa: BLE001
        pass

    # CRÍTICO: intentar TODAS las sesiones con tools antes de fallback sin tools.
    # Antes, un fallo en tools:* hacía caer en full:* sin herramientas → CED hablaba pero no ejecutaba.
    tool_attempts: list[tuple[str, dict[str, Any]]] = []
    fallback_attempts: list[tuple[str, dict[str, Any]]] = []
    turn_options = (
        ("semantic", preferred_turn),
        ("semantic_default", REALTIME_TURN_DETECTION),
        ("server_vad", REALTIME_TURN_DETECTION_FALLBACK),
    )
    for m in _models_to_try(model):
        for td_label, td in turn_options:
            tool_attempts.append(
                (
                    f"tools:{td_label}:{m}",
                    _build_session_payload(
                        model=m,
                        voice=voice,
                        instructions=instructions,
                        with_tools=True,
                        turn_detection=td,
                        language=lang,
                        temperature=temperature,
                    ),
                )
            )
            fallback_attempts.append(
                (
                    f"full:{td_label}:{m}",
                    _build_session_payload(
                        model=m,
                        voice=voice,
                        instructions=instructions,
                        with_tools=False,
                        turn_detection=td,
                        language=lang,
                        temperature=temperature,
                    ),
                )
            )
            fallback_attempts.append(
                (
                    f"minimal:{td_label}:{m}",
                    _build_minimal_payload(
                        model=m,
                        voice=voice,
                        instructions=instructions,
                        turn_detection=td,
                        language=lang,
                    ),
                )
            )

    attempts = tool_attempts + fallback_attempts

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
                    session_body = payload.get("session", {})
                    tools_enabled = bool(session_body.get("tools"))
                    if not tools_enabled:
                        logger.warning(
                            "[OPENAI] webrtc session WITHOUT tools via=%s model=%s user=%s",
                            label,
                            used_model,
                            user_id[:8],
                        )
                    else:
                        logger.info(
                            "[OPENAI] webrtc session ok via=%s model=%s voice=%s tools=%s user=%s",
                            label,
                            used_model,
                            voice,
                            len(session_body.get("tools") or []),
                            user_id[:8],
                        )
                    return {
                        "ok": True,
                        "clientSecret": client_secret,
                        "model": used_model,
                        "voiceName": voice,
                        "systemInstruction": instructions,
                        "expiresInSeconds": 600,
                        "transport": "webrtc",
                        "toolsEnabled": tools_enabled,
                        "toolsCount": len(session_body.get("tools") or []),
                        "sessionVia": label,
                        "userAddress": {
                            "displayName": address.get("displayName", ""),
                            "firstName": address.get("firstName", ""),
                            "honorific": address.get("honorific", ""),
                            "gender": address.get("gender"),
                            "preferredAddress": address.get("preferredAddress"),
                            "greetingPhraseJarvis": address.get("greetingPhraseJarvis", ""),
                            "greetingPhraseStandard": address.get("greetingPhraseStandard", ""),
                        },
                    }

                detail = res.text[:400]
                parsed = _parse_openai_error(res)
                logger.error("[OPENAI] session create %s %s: %s", label, res.status_code, detail)
                last_error = f"OpenAI Realtime ({res.status_code}): {parsed}"
    except Exception as exc:  # noqa: BLE001
        logger.exception("[OPENAI] session create failed")
        return {"ok": False, "error": f"No se pudo contactar OpenAI: {exc}"}

    return {"ok": False, "error": last_error}


def negotiate_realtime_call(*, client_secret: str, sdp_offer: str) -> dict[str, Any]:
    """Proxy SDP offer → OpenAI /v1/realtime/calls (evita CORS en el navegador)."""
    secret = client_secret.strip()
    if not secret:
        return {"ok": False, "error": "Falta client secret efímero."}
    if not sdp_offer.strip():
        return {"ok": False, "error": "SDP offer vacío."}

    try:
        with httpx.Client(timeout=45.0) as client:
            res = client.post(
                OPENAI_REALTIME_CALLS_URL,
                content=sdp_offer,
                headers={
                    "Authorization": f"Bearer {secret}",
                    "Content-Type": "application/sdp",
                },
            )
            if res.status_code >= 400:
                return {"ok": False, "error": _parse_openai_error(res)}
            return {"ok": True, "sdpAnswer": res.text}
    except Exception as exc:  # noqa: BLE001
        logger.exception("[OPENAI] realtime call negotiate failed")
        return {"ok": False, "error": f"No se pudo negociar WebRTC: {exc}"}
