"""Cámara y mapa son órdenes distintas del silencio.

Encender la cámara es UNA frase: «CED enciende la cámara».
GRABAR, stop, mira esto, activa, abre o qué ves no la encienden.
"""

from __future__ import annotations

import re
from contextvars import ContextVar

from app.services.cognitive_intents import is_camera_deactivation_intent
from app.services.voice_client_session import last_heard_line
from app.services.voice_cue import is_stop_utterance, mentions_ced_name

CAMERA_MODEL_TOOLS = frozenset(
    {
        "request_camera_activation",
        "analyze_camera_frame",
        "buscar_lo_visible",
    }
)
CAMERA_OFF_TOOLS = frozenset({"request_camera_deactivation"})
MAP_MODEL_TOOLS = frozenset(
    {
        "activar_modo_conducir",
        "search_nearby_places",
        "start_navigation",
    }
)
DEVICE_MODEL_TOOLS = CAMERA_MODEL_TOOLS | CAMERA_OFF_TOOLS | MAP_MODEL_TOOLS

_turn_text: ContextVar[str] = ContextVar("ced_voice_turn_text", default="")

_ENCIENDE_CAMARA = re.compile(
    r"\benciende(?:r|a)?\s+(?:la\s+)?c[aá]mara\b",
    re.I,
)
_CAMERA_VISION = re.compile(
    r"\b(?:mira\s+esto|m[ií]rame|qu[eé]\s+ves|qu[eé]\s+veo|describe\s+lo\s+que\s+ves)\b",
    re.I,
)
_MAP_OPEN = re.compile(
    r"\b(?:abre(?:r)?|activa(?:r)?|muestra(?:r)?)\s+(?:el\s+)?mapa\b|"
    r"\bmodo\s+conducir\b|"
    r"\bll[eé]vame\s+a\b|"
    r"\bnavega(?:r)?\s+a\b|"
    r"\bc[oó]mo\s+llego\b",
    re.I,
)


def set_turn_text(text: str) -> None:
    """Frase de ESTE turno. La cámara no hereda la frase anterior."""
    _turn_text.set((text or "").strip())


def current_turn_text() -> str:
    return _turn_text.get()


def is_camera_open_phrase(text: str) -> bool:
    """Única orden que enciende la cámara: CED + enciende la cámara."""
    heard = (text or "").strip()
    if not heard or is_stop_utterance(heard):
        return False
    if is_camera_deactivation_intent(heard):
        return False
    if not mentions_ced_name(heard):
        return False
    return bool(_ENCIENDE_CAMARA.search(heard))


def is_camera_vision_phrase(text: str) -> bool:
    heard = (text or "").strip()
    if not heard or is_stop_utterance(heard):
        return False
    return bool(_CAMERA_VISION.search(heard))


def is_map_open_phrase(text: str) -> bool:
    heard = (text or "").strip()
    if not heard or is_stop_utterance(heard):
        return False
    return bool(_MAP_OPEN.search(heard))


def device_tools_for_turn(text: str) -> frozenset[str]:
    """Herramientas de dispositivo que este turno puede usar. El resto se quita."""
    if is_stop_utterance(text):
        return frozenset()
    keep: set[str] = set()
    if is_camera_open_phrase(text):
        keep.add("request_camera_activation")
    if is_camera_vision_phrase(text):
        keep.update({"analyze_camera_frame", "buscar_lo_visible"})
    if is_camera_deactivation_intent(text):
        keep.update(CAMERA_OFF_TOOLS)
    if is_map_open_phrase(text):
        keep.update(MAP_MODEL_TOOLS)
    return frozenset(keep)


def _blocked_by_stop(user_id: str) -> bool:
    latest = last_heard_line(user_id).strip()
    return bool(latest and is_stop_utterance(latest))


def camera_open_allowed(user_id: str, heard: str = "") -> bool:
    from app.services.voice_client_session import voice_is_held

    if voice_is_held(user_id) or _blocked_by_stop(user_id) or is_stop_utterance(heard):
        return False
    latest = last_heard_line(user_id).strip()
    text = (latest or heard or current_turn_text()).strip()
    if not text or is_stop_utterance(text):
        return False
    return is_camera_open_phrase(text)


def map_open_allowed(user_id: str, heard: str = "") -> bool:
    from app.services.voice_client_session import voice_is_held

    if voice_is_held(user_id) or _blocked_by_stop(user_id) or is_stop_utterance(heard):
        return False
    latest = last_heard_line(user_id).strip()
    text = (latest or heard or current_turn_text()).strip()
    if not text or is_stop_utterance(text):
        return False
    return is_map_open_phrase(text)


def user_asked_for_camera(text: str) -> bool:
    return is_camera_open_phrase(text)


def user_asked_for_map(text: str) -> bool:
    return is_map_open_phrase(text)


_CAMERA_ON_ANNOUNCE = re.compile(
    r"\b(?:activ(?:e|a|ando)|encend(?:[ií]|iendo)|prend(?:[ií]|iendo))\s+"
    r"(?:la\s+)?c[aá]mara\b|"
    r"\bc[aá]mara\s+(?:est[aá]\s+)?(?:activa|encendida|prendida|lista|abierta)\b",
    re.I,
)


def is_camera_on_announcement(text: str) -> bool:
    """True si la frase anuncia que la cámara ya está o se está encendiendo."""
    t = (text or "").strip()
    if not t:
        return False
    if re.search(r"(?i)\bno\s+est[aá]\s+(?:activa|encendida)\b", t):
        return False
    return bool(_CAMERA_ON_ANNOUNCE.search(t))


def silence_camera_status_speech(text: str, user_id: str = "") -> bool:
    """Silencio: CED no puede decir que la cámara está on si este turno no es la orden."""
    if not is_camera_on_announcement(text):
        return False
    from app.services.voice_client_session import voice_is_held

    heard = last_heard_line(user_id) if user_id else current_turn_text()
    if voice_is_held(user_id) or is_stop_utterance(heard):
        return True
    return not is_camera_open_phrase(heard)
