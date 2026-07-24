"""Tests — pulido de comandos de voz (detección + cámara)."""

from __future__ import annotations

from app.services.cognitive_intents import is_camera_voice_command
from app.services.module_detector import CONF_ANCHOR, detect_intent
from app.services.retell_custom_llm import resolve_camera_voice_request


def test_finance_voice_phrase_anchor():
    phrase = "Oye, ¿qué tengo en finanzas? Dame un reporte"
    d = detect_intent(phrase, classify=None, run_stage2=False)
    assert d.module == "finance"
    assert d.confidence == CONF_ANCHOR
    assert d.activate is True


def test_camera_voice_command_detects_activation():
    assert is_camera_voice_command("activa la cámara")
    assert resolve_camera_voice_request("activa la cámara") is not None
