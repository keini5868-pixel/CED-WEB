"""Tests — intención activar cámara por voz."""

from __future__ import annotations

from app.services.cognitive_intents import is_camera_activation_intent


def test_activa_la_camara():
    assert is_camera_activation_intent("activa la cámara")
    assert is_camera_activation_intent("Activa la camara por favor")
    assert is_camera_activation_intent("enciende la cámara")


def test_not_activation_when_analyze():
    assert not is_camera_activation_intent("¿qué ves en la cámara?")
    assert not is_camera_activation_intent("apaga la cámara")
