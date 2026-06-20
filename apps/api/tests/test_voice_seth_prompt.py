"""Tests — prompt Seth activo y rutas conversacionales no transaccionales."""

from app.domain.openai_voice_prompt import build_ced_voice_system_prompt, voice_prompt_diagnostics
from app.services.retell_custom_llm import (
    concise_reply_for_small_talk,
    empathetic_fallback_reply,
    is_casual_conversation,
)


def test_voice_prompt_includes_seth_and_anti_transactional():
    prompt = build_ced_voice_system_prompt()
    assert "Seth" in prompt
    assert "Castillo de la Evolución Digital" in prompt
    assert "bot transaccional" in prompt
    diag = voice_prompt_diagnostics()
    assert diag["includes_seth"] is True
    assert diag["includes_anti_transactional"] is True
    assert diag["prompt_chars"] > 4000


def test_casual_conversation_detects_tired_day():
    text = "Seth, hoy fue un día bastante agotador y me siento cansado"
    assert is_casual_conversation(text)


def test_empathetic_fallback_avoids_transactional_phrase():
    tired = empathetic_fallback_reply("Hoy dormí tres horas porque estaba cansado")
    assert "en qué puedo ayudarle" not in tired.lower()
    assert "señor" in tired.lower()

    hello = concise_reply_for_small_talk("hola cómo estás")
    assert "en qué puedo ayudarle" not in hello.lower()
