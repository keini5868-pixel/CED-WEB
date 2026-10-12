"""Tests — la cámara solo se enciende con «CED enciende la cámara»."""

from __future__ import annotations

from app.services.cognitive_intents import is_camera_activation_intent
from app.services.voice_device_gate import is_camera_open_phrase


def test_only_ced_enciende_opens_the_camera():
    assert is_camera_open_phrase("CED enciende la cámara")
    assert is_camera_activation_intent("ok ced enciende la camara")
    assert is_camera_activation_intent("okay set enciende la cámara")


def test_other_phrases_do_not_open_the_camera():
    for phrase in (
        "activa la cámara",
        "Activa la camara por favor",
        "enciende la cámara",
        "abre la cámara",
        "mira esto",
        "¿qué ves en la cámara?",
        "apaga la cámara",
        "stop",
        "estop",
        "GRABAR",
        "ok ced stop",
    ):
        assert not is_camera_activation_intent(phrase)
        assert not is_camera_open_phrase(phrase)
