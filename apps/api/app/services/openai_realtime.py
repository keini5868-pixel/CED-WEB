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
    REALTIME_TURN_DETECTION,
    REALTIME_TURN_DETECTION_FALLBACK,
    normalize_openai_voice,
    profile_for_response_speed,
)
from app.services.openai_voice_tools import (
    OPENAI_REALTIME_TOOLS,
    fitline_cierre_realtime_tools,
)

logger = logging.getLogger(__name__)

OPENAI_CLIENT_SECRETS_URL = "https://api.openai.com/v1/realtime/client_secrets"
OPENAI_REALTIME_CALLS_URL = "https://api.openai.com/v1/realtime/calls"

DEFAULT_REALTIME_MODEL = "gpt-realtime"
# FitLine/Cierre: mini es más barato y válido en Realtime (no usar gpt-4.1-mini chat).
DEFAULT_FITLINE_REALTIME_MODEL = "gpt-realtime-mini"
FALLBACK_MODELS = (
    "gpt-realtime-mini",
    "gpt-realtime",
    "gpt-4o-mini-realtime-preview-2024-12-17",
    "gpt-4o-realtime-preview-2024-12-17",
)
# Cierre: solo mini (nunca gpt-realtime full ni previews caros).
FITLINE_FALLBACK_MODELS = (
    "gpt-realtime-mini",
    "gpt-4o-mini-realtime-preview-2024-12-17",
)

EXPIRES_AFTER = {"anchor": "created_at", "seconds": 600}

_REALTIME_ALIASES = {
    "gpt-4o-mini-realtime-preview": "gpt-4o-mini-realtime-preview-2024-12-17",
    "gpt-4o-realtime-preview": "gpt-4o-realtime-preview-2024-12-17",
}


def _is_realtime_model(model: str) -> bool:
    """Chat models (gpt-4.1-mini, gpt-4o, …) no sirven en /v1/realtime/*."""
    m = (model or "").strip().lower()
    if not m:
        return False
    if "realtime" in m:
        return True
    # Alias corto oficial OpenAI
    return m in {"gpt-realtime", "gpt-realtime-mini"}


def _resolve_model(settings_model: str, *, prefer_mini: bool = False) -> str:
    raw = (settings_model or "").strip()
    model = _REALTIME_ALIASES.get(raw, raw)
    if not _is_realtime_model(model):
        fallback = DEFAULT_FITLINE_REALTIME_MODEL if prefer_mini else DEFAULT_REALTIME_MODEL
        if raw:
            logger.warning(
                "[OPENAI] OPENAI_MODEL_VOICE=%r no es Realtime — usando %s",
                raw,
                fallback,
            )
        return fallback
    if prefer_mini and model == DEFAULT_REALTIME_MODEL:
        return DEFAULT_FITLINE_REALTIME_MODEL
    return model


def _models_to_try(primary: str, *, mini_only: bool = False) -> list[str]:
    fallbacks = FITLINE_FALLBACK_MODELS if mini_only else FALLBACK_MODELS
    ordered = [primary, *fallbacks]
    seen: set[str] = set()
    out: list[str] = []
    for m in ordered:
        resolved = _REALTIME_ALIASES.get(m, m)
        if resolved and resolved not in seen and _is_realtime_model(resolved):
            if mini_only and "mini" not in resolved.lower():
                continue
            seen.add(resolved)
            out.append(resolved)
    return out or [DEFAULT_FITLINE_REALTIME_MODEL]


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
    tools: list[dict[str, Any]] | None = None,
    max_output_tokens: int | None = None,
    instructions_cap: int = 12000,
) -> dict[str, Any]:
    session: dict[str, Any] = {
        "type": "realtime",
        "model": model,
        "instructions": instructions[:instructions_cap],
        "output_modalities": ["audio"],
        "audio": {
            "input": _audio_input(turn_detection, language=language),
            "output": {
                "voice": voice,
            },
        },
        "max_output_tokens": max_output_tokens or REALTIME_MAX_OUTPUT_TOKENS,
    }
    if with_tools:
        session["tools"] = list(tools) if tools is not None else OPENAI_REALTIME_TOOLS
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
    profile = (voice_profile or "jarvis").strip().lower()
    # CED Cierre / FitLine: SIEMPRE mini + tools lean (cero gasto Tavily/imagen/maps).
    is_fitline = profile == "fitline"
    prefer_mini = is_fitline or profile == "standard"
    model = _resolve_model(settings.openai_model_voice, prefer_mini=prefer_mini)
    if is_fitline:
        model = DEFAULT_FITLINE_REALTIME_MODEL
    project_id = getattr(settings, "openai_project_id", "") or ""

    instructions = build_realtime_instructions(
        language=language or "es",
        voice_pace=voice_pace,
        voice_warmth=voice_warmth,
        voice_energy=voice_energy,
        response_speed=response_speed or "balanced",
        voice_profile=profile or "jarvis",
        user_id=user_id,
    )
    lang = language or "es"
    _temperature, preferred_turn = profile_for_response_speed(response_speed)
    address: dict[str, Any] = {}
    # FitLine: no inyectar extras cognitivos (ahorro de tokens / sin side-effects).
    if not is_fitline:
        try:
            from app.services.cognitive_router import build_voice_system_extras
            from app.services.user_address import resolve_user_address

            extras = build_voice_system_extras(user_id)
            if extras:
                instructions = f"{instructions}\n\n{extras}"
            address = resolve_user_address(user_id)
        except Exception:  # noqa: BLE001
            pass
    else:
        try:
            from app.services.user_address import resolve_user_address

            address = resolve_user_address(user_id)
        except Exception:  # noqa: BLE001
            pass

    session_tools = fitline_cierre_realtime_tools() if is_fitline else OPENAI_REALTIME_TOOLS
    max_out = 700 if is_fitline else None
    instr_cap = 9000 if is_fitline else 12000

    # CRÍTICO: intentar TODAS las sesiones con tools antes de fallback sin tools.
    # Antes, un fallo en tools:* hacía caer en full:* sin herramientas → CED hablaba pero no ejecutaba.
    tool_attempts: list[tuple[str, dict[str, Any]]] = []
    turn_options = (
        ("server_vad", preferred_turn),
        ("server_vad_default", REALTIME_TURN_DETECTION),
        ("semantic_fallback", REALTIME_TURN_DETECTION_FALLBACK),
    )
    models_ordered = (
        _models_to_try(DEFAULT_FITLINE_REALTIME_MODEL, mini_only=True)
        if is_fitline
        else _models_to_try(model)
    )
    for m in models_ordered:
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
                        tools=session_tools,
                        max_output_tokens=max_out,
                        instructions_cap=instr_cap,
                    ),
                )
            )

    attempts = tool_attempts

    last_error = "OpenAI rechazó la sesión Realtime con herramientas."
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
                        continue
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
                        "toolsEnabled": True,
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
