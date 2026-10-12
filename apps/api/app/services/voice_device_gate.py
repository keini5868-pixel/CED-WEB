"""Cámara y mapa solo si la frase lo pide.

«stop», «etop» y «okay set stop» no son una orden de cámara ni de mapa.
Un tool call del modelo no abre el dispositivo por sí solo.
"""

from __future__ import annotations

import re

from app.services.cognitive_intents import (
    is_camera_activation_intent,
    is_camera_deactivation_intent,
    is_camera_voice_command,
)
from app.services.navigation_voice_intent import resolve_open_map_request
from app.services.retell_custom_llm import resolve_camera_voice_request
from app.services.voice_client_session import (
    last_heard_line,
    stop_heard_recently,
)
from app.services.voice_cue import utterance_ends_with_silence

_MAP_ASK = re.compile(
    r"\b(?:abre(?:r)?|activar|muestra(?:r)?|pon(?:er)?)\s+(?:el\s+)?mapa\b|"
    r"\bmodo\s+conducir\b|"
    r"\bll[eé]vame\b|"
    r"\bnavega(?:r)?\b|"
    r"\bc[oó]mo\s+llego\b",
    re.I,
)


def user_asked_for_camera(text: str) -> bool:
    heard = (text or "").strip()
    if not heard or utterance_ends_with_silence(heard):
        return False
    if is_camera_deactivation_intent(heard):
        return False
    if is_camera_activation_intent(heard) or is_camera_voice_command(heard):
        return True
    return resolve_camera_voice_request(heard) is not None


def user_asked_for_map(text: str) -> bool:
    heard = (text or "").strip()
    if not heard or utterance_ends_with_silence(heard):
        return False
    if resolve_open_map_request(heard):
        return True
    return bool(_MAP_ASK.search(heard))


def _latest(user_id: str, heard: str) -> str:
    return (heard or last_heard_line(user_id) or "").strip()


def camera_open_allowed(user_id: str, heard: str = "") -> bool:
    latest = last_heard_line(user_id).strip()
    if latest and utterance_ends_with_silence(latest):
        return False
    if stop_heard_recently(user_id) and not user_asked_for_camera(latest):
        return False
    return user_asked_for_camera(_latest(user_id, heard))


def map_open_allowed(user_id: str, heard: str = "") -> bool:
    latest = last_heard_line(user_id).strip()
    if latest and utterance_ends_with_silence(latest):
        return False
    if stop_heard_recently(user_id) and not user_asked_for_map(latest):
        return False
    return user_asked_for_map(_latest(user_id, heard))
