"""Cámara y mapa son órdenes distintas del silencio.

El modelo no recibe esas herramientas si la frase no las pidió.
«stop» no comparte lista con «abre la cámara» ni con «abre el mapa».
"""

from __future__ import annotations

import re
from contextvars import ContextVar

from app.services.cognitive_intents import is_camera_deactivation_intent
from app.services.voice_client_session import last_heard_line
from app.services.voice_cue import is_stop_utterance

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

_CAMERA_OPEN = re.compile(
    r"\b(?:activa(?:r|me)?|activo|enciende(?:r)?|prende(?:r)?|abre(?:r)?)\b"
    r".{0,30}\b(?:c[aá]mara|camara)\b|"
    r"\b(?:c[aá]mara|camara)\b.{0,20}\b(?:activa|enciende|prende|abre)\b",
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
    heard = (text or "").strip()
    if not heard or is_stop_utterance(heard):
        return False
    if is_camera_deactivation_intent(heard):
        return False
    return bool(_CAMERA_OPEN.search(heard))


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
    if is_camera_open_phrase(text) or is_camera_vision_phrase(text):
        keep.update(CAMERA_MODEL_TOOLS)
    if is_camera_deactivation_intent(text):
        keep.update(CAMERA_OFF_TOOLS)
    if is_map_open_phrase(text):
        keep.update(MAP_MODEL_TOOLS)
    return frozenset(keep)


def _blocked_by_stop(user_id: str) -> bool:
    latest = last_heard_line(user_id).strip()
    return bool(latest and is_stop_utterance(latest))


def camera_open_allowed(user_id: str, heard: str = "") -> bool:
    if _blocked_by_stop(user_id):
        return False
    text = (heard or current_turn_text()).strip()
    if not text:
        return False
    return is_camera_open_phrase(text) or is_camera_vision_phrase(text)


def map_open_allowed(user_id: str, heard: str = "") -> bool:
    if _blocked_by_stop(user_id):
        return False
    text = (heard or current_turn_text()).strip()
    if not text:
        return False
    return is_map_open_phrase(text)


def user_asked_for_camera(text: str) -> bool:
    return is_camera_open_phrase(text) or is_camera_vision_phrase(text)


def user_asked_for_map(text: str) -> bool:
    return is_map_open_phrase(text)
