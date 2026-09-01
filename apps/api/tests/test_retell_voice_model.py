"""Retell voice_model debe limpiarse al volver a voces Cartesia/custom."""

from app.services.retell_agent_setup import (
    CED_JARVIS_CUSTOM_VOICE_ID,
    _apply_voice_model_to_payload,
    _voice_model_for,
)


def test_voice_model_none_for_custom_cartesia_clone():
    assert _voice_model_for(CED_JARVIS_CUSTOM_VOICE_ID) is None


def test_apply_voice_model_clears_payload_for_custom_voice():
    payload: dict = {"voice_id": CED_JARVIS_CUSTOM_VOICE_ID}
    _apply_voice_model_to_payload(payload, CED_JARVIS_CUSTOM_VOICE_ID)
    assert payload["voice_model"] is None


def test_apply_voice_model_sets_eleven_for_builtin():
    payload: dict = {"voice_id": "11labs-Brian"}
    _apply_voice_model_to_payload(payload, "11labs-Brian")
    assert payload["voice_model"]
