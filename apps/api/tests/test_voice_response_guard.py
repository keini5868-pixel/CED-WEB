"""Tests voice response guard tool leak filter (P6)."""

from app.services.voice_response_guard import contains_tool_leak, guard_voice_response


def test_blocks_tool_invoke():
    assert contains_tool_leak("buscar_direccion(direccion='7904 Kalmer, OAKS')")
    assert contains_tool_leak("publicar_facebook(mensaje='hola')")
    blocked, was = guard_voice_response("buscar_direccion(direccion='x')")
    assert was is True
    assert blocked == ""


def test_allows_natural_speech():
    assert not contains_tool_leak("Publicación enviada con éxito, señor.")
    text, was = guard_voice_response("Publicación enviada con éxito, señor.")
    assert was is False
    assert "Publicación" in text
