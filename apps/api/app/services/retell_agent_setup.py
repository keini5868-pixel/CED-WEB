"""Bootstrap agente Retell CED — Custom LLM (Gemini) + ElevenLabs voice."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings
from app.services.retell_client import get_retell_client

logger = logging.getLogger(__name__)

DEFAULT_VOICE_ID = "11labs-Brian"
JARVIS_CLONED_ELEVENLABS_ID = "UKhFmKblQwXqi7vvaALt"
JARVIS_RETELL_VOICE_NAME = "CED Jarvis"

JARVIS_VOICE_HINTS = (
    "british", "butler", "george", "brian", "daniel", "jarvis", "formal", "deep",
    "adrian", "callum",
)

# Jarvis: voces masculinas británicas ElevenLabs vía Retell (11labs-*)
PREFERRED_RETELL_VOICES = (
    "11labs-Brian",
    "11labs-Callum",
    "11labs-Daniel",
    "11labs-Adrian",
    "openai-Onyx",
    "openai-Echo",
)

# Voces ElevenLabs integradas en Retell (prefijo 11labs-)
RETELL_ELEVENLABS_NAME_MAP = {
    "george": "11labs-George",
    "brian": "11labs-Brian",
    "daniel": "11labs-Daniel",
    "callum": "11labs-Callum",
    "charlie": "11labs-Charlie",
}


def _normalize_voice_id(raw: str) -> str:
    """Quita comillas que a veces se pegan en Railway (RETELL_VOICE_ID=\"...\")."""
    return (raw or "").strip().strip('"').strip("'").strip()


def search_jarvis_voices(client: Any, *, query: str = "") -> list[dict[str, str]]:
    """Voces en Retell llamadas Jarvis o ligadas al ID ElevenLabs del clon."""
    q = (query or JARVIS_CLONED_ELEVENLABS_ID).lower()
    matches: list[dict[str, str]] = []
    for voice in _list_retell_voices(client):
        vid = _voice_field(voice, "voice_id")
        if not vid:
            continue
        name = _voice_field(voice, "voice_name").strip()
        raw = str(voice).lower()
        if "jarvis" in name.lower():
            matches.append({"voice_id": vid, "voice_name": name})
        elif q and q in raw:
            matches.append({"voice_id": vid, "voice_name": name})
    return matches


def resolve_configured_retell_voice_id(client: Any, configured: str) -> str:
    """RETELL_VOICE_ID → voice_id válido en Retell (mapea ElevenLabs o busca Jarvis)."""
    cleaned = _normalize_voice_id(configured)
    if not cleaned:
        return resolve_retell_voice_id_from_api(client)

    if cleaned.startswith(("custom_voice_", "11labs-", "openai-", "retell-", "cartesia-", "minimax-")):
        return cleaned

    mapped = find_retell_voice_by_elevenlabs_id(client, cleaned)
    if mapped:
        logger.info("[RETELL] ElevenLabs %s → Retell %s", cleaned, mapped)
        return mapped

    for entry in search_jarvis_voices(client, query=cleaned):
        if "jarvis" in entry["voice_name"].lower():
            logger.info("[RETELL] voz Jarvis en biblioteca: %s", entry["voice_id"])
            return entry["voice_id"]

    return cleaned


def find_retell_voice_by_elevenlabs_id(client: Any, elevenlabs_id: str) -> str | None:
    """Busca en la biblioteca Retell la voz cuyo provider_voice_id coincide."""
    target = _normalize_voice_id(elevenlabs_id)
    if not target:
        return None
    for voice in _list_retell_voices(client):
        vid = _voice_field(voice, "voice_id")
        if not vid:
            continue
        if _voice_field(voice, "provider_voice_id") == target:
            return vid
        if target in str(voice):
            return vid
    return None


def _voice_field(voice: Any, key: str) -> str:
    if isinstance(voice, dict):
        return str(voice.get(key) or "")
    return str(getattr(voice, key, None) or "")


def _list_retell_voices(client: Any) -> list[Any]:
    try:
        listed = client.voice.list()
        voices = getattr(listed, "voices", None) or listed
        if not isinstance(voices, list):
            return list(voices) if voices else []
        return voices
    except Exception as exc:  # noqa: BLE001
        logger.warning("[RETELL] voice.list failed: %s", exc)
        return []


def ensure_jarvis_voice_in_retell(client: Any) -> tuple[str | None, str | None]:
    """Registra el clon Jarvis (ElevenLabs) en Retell. Retorna (voice_id, error)."""
    settings = get_settings()
    el_id = (
        settings.elevenlabs_jarvis_voice_id.strip() or JARVIS_CLONED_ELEVENLABS_ID
    ).strip()
    if not el_id:
        return None, "ELEVENLABS_JARVIS_VOICE_ID vacío"

    for voice in _list_retell_voices(client):
        vid = _voice_field(voice, "voice_id")
        if not vid:
            continue
        if vid == el_id:
            return vid, None
        if _voice_field(voice, "provider_voice_id") == el_id:
            return vid, None
        name = _voice_field(voice, "voice_name").lower()
        if "ced jarvis" in name:
            return vid, None
        raw = str(voice)
        if el_id in raw:
            return vid, None

    payload: dict[str, Any] = {
        "provider_voice_id": el_id,
        "voice_name": JARVIS_RETELL_VOICE_NAME,
        "voice_provider": "elevenlabs",
    }
    public_uid = settings.elevenlabs_jarvis_public_user_id.strip()
    if public_uid:
        payload["public_user_id"] = public_uid

    try:
        added = client.voice.add_resource(**payload)
        vid = _voice_field(added, "voice_id")
        if vid:
            logger.info("[RETELL] Clon Jarvis registrado en Retell: %s (el=%s)", vid, el_id)
            return vid, None
        return None, "add_resource no devolvió voice_id"
    except Exception as exc:  # noqa: BLE001
        err = str(exc)
        logger.warning(
            "[RETELL] No se pudo registrar clon Jarvis %s: %s",
            el_id,
            err,
        )
        if "public_user_id" in err.lower() or "community" in err.lower():
            err = (
                f"{err} — La voz debe ser pública en ElevenLabs o agregue "
                "ELEVENLABS_JARVIS_PUBLIC_USER_ID en Railway."
            )
        elif "private" in err.lower() or "not found" in err.lower():
            err = (
                f"{err} — Agregue la voz manualmente en Retell (Add custom voice) "
                f"con ID {el_id} y fije RETELL_VOICE_ID al ID que asigne Retell."
            )
        return None, err


def resolve_retell_voice_id_from_api(client: Any) -> str:
    """Lista voces Retell y elige la mejor Jarvis disponible (ignora env inválido)."""
    try:
        voices = _list_retell_voices(client)
    except Exception:  # noqa: BLE001
        return DEFAULT_VOICE_ID

    available: list[str] = []
    for voice in voices:
        if isinstance(voice, dict):
            vid = str(voice.get("voice_id") or voice.get("id") or "")
            name = str(voice.get("voice_name") or voice.get("name") or "").lower()
            provider = str(voice.get("provider") or "").lower()
        else:
            vid = str(getattr(voice, "voice_id", None) or getattr(voice, "id", "") or "")
            name = str(getattr(voice, "voice_name", None) or getattr(voice, "name", "") or "").lower()
            provider = str(getattr(voice, "provider", None) or "").lower()
        if not vid:
            continue
        available.append(vid)

    available_set = set(available)
    for preferred in PREFERRED_RETELL_VOICES:
        if preferred in available_set:
            logger.info("[RETELL] voice preferida: %s", preferred)
            return preferred

    best_id = DEFAULT_VOICE_ID
    best_score = -1
    for voice in voices:
        if isinstance(voice, dict):
            vid = str(voice.get("voice_id") or voice.get("id") or "")
            name = str(voice.get("voice_name") or voice.get("name") or "").lower()
            provider = str(voice.get("provider") or "").lower()
        else:
            vid = str(getattr(voice, "voice_id", None) or getattr(voice, "id", "") or "")
            name = str(getattr(voice, "voice_name", None) or getattr(voice, "name", "") or "").lower()
            provider = str(getattr(voice, "provider", None) or "").lower()
        if not vid:
            continue
        if vid in PREFERRED_RETELL_VOICES:
            return vid
        haystack = f"{name} {vid.lower()} {provider}"
        score = sum(1 for hint in JARVIS_VOICE_HINTS if hint in haystack)
        if "11labs" in haystack or "eleven" in provider:
            score += 2
        if "male" in haystack or "man" in haystack:
            score += 1
        if score > best_score:
            best_score = score
            best_id = vid

    logger.info("[RETELL] voice seleccionada: %s (score=%s)", best_id, best_score)
    return best_id


def resolve_retell_voice_id(client: Any | None = None) -> str:
    settings = get_settings()
    configured = settings.retell_voice_id.strip()
    if configured:
        return configured
    if client is not None:
        return resolve_retell_voice_id_from_api(client)
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
    return f"{ws_base}/llm-websocket"


def _voice_model_for(voice_id: str) -> str | None:
    """Modelo TTS compatible con el proveedor de la voz Retell."""
    if voice_id.startswith("openai-"):
        return "tts-1"
    return "eleven_turbo_v2_5"


def ensure_retell_agent(*, agent_id: str | None = None) -> dict[str, str]:
    """Crea o actualiza agente Retell con Custom LLM (Gemini) + ElevenLabs."""
    client = get_retell_client()
    if not client:
        raise RuntimeError("RETELL_API_KEY no configurada")

    settings = get_settings()
    if not settings.google_api_key.strip():
        raise RuntimeError("GOOGLE_API_KEY no configurada — requerida para Gemini voz")

    configured = _normalize_voice_id(settings.retell_voice_id)
    jarvis_error: str | None = None

    if configured:
        voice_id = resolve_configured_retell_voice_id(client, configured)
    else:
        jarvis, jarvis_error = ensure_jarvis_voice_in_retell(client)
        if jarvis:
            voice_id = jarvis
        else:
            voice_id = resolve_retell_voice_id_from_api(client)
    webhook = f"{settings.api_public_url.rstrip('/')}/v1/retell/webhook"
    llm_ws = custom_llm_websocket_url()

    agent_payload: dict[str, Any] = {
        "response_engine": {
            "type": "custom-llm",
            "llm_websocket_url": llm_ws,
        },
        "voice_id": voice_id,
        "voice_model": _voice_model_for(voice_id),
        "voice_speed": 1.0,
        "responsiveness": 0.95,
        "interruption_sensitivity": 0.85,
        "language": "multi",
        "stt_mode": "fast",
        "webhook_url": webhook,
        "webhook_events": ["call_started", "call_ended", "call_analyzed"],
        "begin_message_delay_ms": 0,
        "agent_name": "CED Jarvis",
    }

    if agent_id:
        try:
            client.agent.update(agent_id=agent_id, **agent_payload)
        except Exception as exc:
            if "not found from voice" in str(exc).lower():
                if configured:
                    raise RuntimeError(
                        f"RETELL_VOICE_ID={configured!r} no es válido en Retell. "
                        "Use el voice_id que asignó Retell al agregar la voz (no el ID de ElevenLabs). "
                        f"Detalle: {exc}"
                    ) from exc
                voice_id = resolve_retell_voice_id_from_api(client)
                agent_payload["voice_id"] = voice_id
                client.agent.update(agent_id=agent_id, **agent_payload)
            else:
                raise
        logger.info("[RETELL] Agente actualizado: %s voice=%s ws=%s", agent_id, voice_id, llm_ws)
        out = {
            "agent_id": agent_id,
            "voice_id": voice_id,
            "llm_websocket_url": llm_ws,
            "brain": settings.gemini_voice_model,
        }
        if jarvis_error:
            out["jarvis_voice_error"] = jarvis_error
        if configured:
            out["configured_voice_id"] = configured
        return out

    try:
        created = client.agent.create(**agent_payload)
    except Exception as exc:
        if "not found from voice" in str(exc).lower():
            if configured:
                raise RuntimeError(
                    f"RETELL_VOICE_ID={configured!r} no es válido en Retell. "
                    "Use el voice_id que asignó Retell al agregar la voz. "
                    f"Detalle: {exc}"
                ) from exc
            voice_id = resolve_retell_voice_id_from_api(client)
            agent_payload["voice_id"] = voice_id
            created = client.agent.create(**agent_payload)
        else:
            raise
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

    from app.services.retell_agent_cache import set_bootstrapped_agent, set_bootstrap_error

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
        msg = str(exc)
        set_bootstrap_error(msg)
        logger.error("[RETELL] bootstrap failed: %s", msg, exc_info=True)
        return None


def bootstrap_retell_on_startup() -> None:
    """Actualiza agente existente si RETELL_AUTO_BOOTSTRAP=true."""
    settings = get_settings()
    if not settings.retell_auto_bootstrap:
        return
    bootstrap_retell_if_needed()
