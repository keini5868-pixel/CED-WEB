"""Tests para respuestas instantáneas de small talk en voz."""

from app.services.voice_small_talk import try_instant_small_talk_voice_reply


def test_como_estas_instant():
    reply = try_instant_small_talk_voice_reply("¿Cómo estás?")
    assert reply
    assert "señor" in reply.lower()


def test_hola_instant():
    reply = try_instant_small_talk_voice_reply("hola")
    assert reply
    assert "señor" in reply.lower()


def test_task_query_not_instant():
    assert try_instant_small_talk_voice_reply("llévame a Charlotte") is None
